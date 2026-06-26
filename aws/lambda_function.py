"""
AWS Lambda - SharePoint to Splunk HEC Integration
Pulls compliance data from SharePoint, normalizes it to the dashboard-compatible
11-column format, sends to Splunk HEC, stores dated S3 snapshots, and writes
achievement records when a milestone transitions from On Roadmap to Compliant.
Triggered by EventBridge Scheduler (daily at 6 AM UTC).
"""

import io
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import boto3
import pandas as pd
import requests
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SHAREPOINT_SITE_PATH = "cisco.sharepoint.com:/sites/Splunk-Product-Compliance"
FILE_ID              = "F07872BA-6EA5-40D0-A837-4A6505B4F336"
WORKSHEET_NAME       = "Compliance Inventory"
SECRET_PREFIX        = os.environ.get("SECRET_PREFIX", "sharepoint-compliance")
AWS_REGION           = os.environ.get("AWS_REGION", "us-east-1")
S3_DATA_BUCKET       = os.environ.get("S3_DATA_BUCKET", "")
DYNAMODB_CHANGES_TABLE = os.environ.get("DYNAMODB_CHANGES_TABLE", "sharepoint-compliance-changes")
ACHIEVEMENTS_TABLE   = os.environ.get("ACHIEVEMENTS_TABLE", "sharepoint-compliance-achievements")

# Number of leading columns in the raw worksheet that are entity identifiers
# (In production?, Product, Feature, Product Area, Infrastructure)
N_ENTITY_COLS = int(os.environ.get("N_ENTITY_COLS", "5"))

# Normalized column names — must match dashboard/lookup expectations
COL_PRODUCT     = "Product"
COL_FEATURE     = "Feature"
COL_AREA        = "Product Area"
COL_INFRA       = "Infrastructure"
COL_REGION      = "Region"
COL_CATEGORY    = "Category"
COL_SUBCATEGORY = "Subcategory"
COL_CERT        = "Certification"
COL_STATUS      = "Compliance Status"
COL_QUARTER     = "Roadmap Quarter"
COL_NOTES       = "Additional Information (Notes)"

# Dashboard-compatible status strings
STATUS_COMPLIANT     = "Compliant"
STATUS_ON_ROADMAP    = "On Roadmap"
STATUS_NA            = "Not Applicable"
STATUS_NOT_COMPLIANT = "Not Compliant"

# Cell value patterns
_QUARTER_RE          = re.compile(r"Q[1-4]FY\d{2}", re.IGNORECASE)
_COMPLIANT_CELL_VALS = {"✓", "✔", "✓*", "yes", "compliant", "done", "complete", "completed"}
_NA_CELL_VALS        = {"not applicable", "n/a", "na", ""}
_NOT_COMPLIANT_VALS  = {"not compliant", "non-compliant"}


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------
def get_secret(secret_id: str) -> str:
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=secret_id)
    return response["SecretString"]


# ---------------------------------------------------------------------------
# SharePoint / Graph API
# ---------------------------------------------------------------------------
def get_access_token(client_id: str, client_secret: str, tenant_id: str) -> str:
    print("Getting SharePoint access token...")
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    resp.raise_for_status()
    print("  Access token obtained")
    return resp.json()["access_token"]


def get_site_id(access_token: str, site_path: str) -> str:
    print(f"Getting site ID for: {site_path}")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_path}",
        headers=headers, timeout=30,
    )
    resp.raise_for_status()
    info = resp.json()
    print(f"  Site: {info.get('displayName')}")
    return info["id"]


def get_worksheet_data(access_token: str, site_id: str, file_id: str,
                       worksheet_name: str) -> pd.DataFrame:
    """
    Fetch the worksheet usedRange and return a DataFrame with clean column names.

    Excel layout (0-indexed rows from usedRange):
      Row 0: ignored extra row
      Row 1: region/category labels  (Global, AMER, EMEA, ...)
      Row 2: subcategory labels      (Healthcare, US Commercial, ...)
      Row 3: actual column names     (Product, Feature, ..., SOC 2, HIPAA, ...)
      Row 4+: data
    """
    print(f"Reading worksheet: {worksheet_name}")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/items/{file_id}/workbook/worksheets('{worksheet_name}')/usedRange"
    )
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()

    values = resp.json().get("values", [])
    if len(values) < 5:
        raise ValueError(f"Insufficient rows in worksheet (got {len(values)})")

    # Row 3 has the actual column names; use them directly so they match cert_mappings keys
    row3 = values[3]
    # Normalize known column name variations from the Excel file
    _COL_ALIASES = {"Product_Area": "Product Area"}
    column_names = [
        _COL_ALIASES.get(str(row3[i]).strip(), str(row3[i]).strip()) if row3[i] else f"Column_{i}"
        for i in range(len(row3))
    ]

    df = pd.DataFrame(values[4:], columns=column_names)
    print(f"  Retrieved {len(df)} rows, {len(df.columns)} columns")
    return df


# ---------------------------------------------------------------------------
# Certification metadata
# ---------------------------------------------------------------------------
def get_certification_mappings() -> dict:
    """Map cert name -> {Region, Category, Subcategory}. Mirrors GCP processing logic."""
    return {
        "SOC 2":                  {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "SOC 1":                  {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "ISO 27001":              {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "ISO 27017":              {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "ISO 27018":              {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "ISO 9001":               {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "ISO 42001":              {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "PCI":                    {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "CSA Star - level 1":     {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "CSA Star - level 2":     {"Region": "Global", "Category": "",                  "Subcategory": ""},
        "HIPAA":                  {"Region": "AMER",   "Category": "US Commercial",     "Subcategory": "Healthcare"},
        "FedRAMP Moderate":       {"Region": "AMER",   "Category": "USPS",              "Subcategory": "US Government & Defense"},
        "FedRAMP High":           {"Region": "AMER",   "Category": "USPS",              "Subcategory": "US Government & Defense"},
        "DoD IL5":                {"Region": "AMER",   "Category": "USPS",              "Subcategory": "US Government & Defense"},
        "GovRAMP":                {"Region": "AMER",   "Category": "USPS",              "Subcategory": "SLED"},
        "TX-RAMP":                {"Region": "AMER",   "Category": "USPS",              "Subcategory": "SLED"},
        "NIAP / Common Criteria": {"Region": "AMER",   "Category": "USPS",              "Subcategory": "On-prem"},
        "ISMAP (Japan)":          {"Region": "APJC",   "Category": "",                  "Subcategory": ""},
        "IRAP (Australia)":       {"Region": "APJC",   "Category": "",                  "Subcategory": ""},
        "TISAX":                  {"Region": "EMEA",   "Category": "",                  "Subcategory": ""},
        "Italian ACN QC1":        {"Region": "EMEA",   "Category": "",                  "Subcategory": ""},
        "Italian ACN QC2":        {"Region": "EMEA",   "Category": "",                  "Subcategory": ""},
        "UAE DESC":               {"Region": "EMEA",   "Category": "",                  "Subcategory": ""},
        "Spain CPSTIC":           {"Region": "EMEA",   "Category": "",                  "Subcategory": ""},
        "FIPS 140-2":             {"Region": "Global", "Category": "Technical Requirements", "Subcategory": ""},
        "FIPS 140-3":             {"Region": "Global", "Category": "Technical Requirements", "Subcategory": ""},
        "IPv6":                   {"Region": "Global", "Category": "Technical Requirements", "Subcategory": ""},
        "TLS 1.3":                {"Region": "Global", "Category": "Technical Requirements", "Subcategory": ""},
    }


# ---------------------------------------------------------------------------
# Cell value parsing
# ---------------------------------------------------------------------------
def parse_cell_value(value) -> tuple:
    """
    Parse a raw cell value into (Compliance Status, Roadmap Quarter, Notes).
    Returns dashboard-compatible status strings.
    """
    v = str(value).strip() if value else ""
    vl = v.lower()

    if vl in _NA_CELL_VALS:
        return STATUS_NA, "", ""
    if vl in _COMPLIANT_CELL_VALS:
        return STATUS_COMPLIANT, "", ""
    if vl in _NOT_COMPLIANT_VALS:
        return STATUS_NOT_COMPLIANT, "", ""

    m = _QUARTER_RE.search(v)
    if m:
        quarter = m.group(0).upper()
        notes = v.replace(m.group(0), "").strip(" -–,")
        return STATUS_ON_ROADMAP, quarter, notes

    # Unrecognized — treat as Not Compliant, preserve raw value in notes
    return STATUS_NOT_COMPLIANT, "", v


# ---------------------------------------------------------------------------
# Normalize raw wide DataFrame to dashboard-compatible 11-column format
# ---------------------------------------------------------------------------
def normalize_to_dashboard_format(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Transforms the raw wide worksheet (one row per product/feature,
    one column per certification) into the normalized format the
    Splunk dashboard and lookup tables expect:

    Product | Feature | Product Area | Infrastructure | Region | Category |
    Subcategory | Certification | Compliance Status | Roadmap Quarter |
    Additional Information (Notes)
    """
    cert_maps = get_certification_mappings()
    cert_cols = list(raw_df.columns[N_ENTITY_COLS:])
    records = []

    for _, row in raw_df.iterrows():
        product      = str(row.get(COL_PRODUCT, "")).strip()
        feature      = str(row.get(COL_FEATURE, "")).strip() or "N/A"
        product_area = str(row.get(COL_AREA, "")).strip()
        infra        = str(row.get(COL_INFRA, "")).strip()

        if not product:
            continue

        for cert_name in cert_cols:
            if not cert_name or cert_name.startswith("Column_"):
                continue

            status, quarter, notes = parse_cell_value(row.get(cert_name, ""))
            mapping = cert_maps.get(cert_name, {"Region": "Global", "Category": "", "Subcategory": ""})

            records.append({
                COL_PRODUCT:     product,
                COL_FEATURE:     feature,
                COL_AREA:        product_area,
                COL_INFRA:       infra,
                COL_REGION:      mapping["Region"],
                COL_CATEGORY:    mapping["Category"],
                COL_SUBCATEGORY: mapping["Subcategory"],
                COL_CERT:        cert_name,
                COL_STATUS:      status,
                COL_QUARTER:     quarter,
                COL_NOTES:       notes,
            })

    norm_df = pd.DataFrame(records)
    print(f"  Normalized to {len(norm_df)} records "
          f"({norm_df[COL_STATUS].value_counts().to_dict()})")
    return norm_df


# ---------------------------------------------------------------------------
# Splunk HEC events (from normalized DataFrame)
# ---------------------------------------------------------------------------
def transform_to_events(norm_df: pd.DataFrame) -> list:
    """Build Splunk HEC event dicts from the normalized DataFrame."""
    print(f"Transforming {len(norm_df)} normalized records to Splunk events...")
    ts = datetime.now(timezone.utc).isoformat()
    events = []
    for _, row in norm_df.iterrows():
        event = {
            "product":            row.get(COL_PRODUCT, ""),
            "feature":            row.get(COL_FEATURE, ""),
            "product_area":       row.get(COL_AREA, ""),
            "infrastructure":     row.get(COL_INFRA, ""),
            "region":             row.get(COL_REGION, ""),
            "category":           row.get(COL_CATEGORY, ""),
            "subcategory":        row.get(COL_SUBCATEGORY, ""),
            "certification":      row.get(COL_CERT, ""),
            "compliance_status":  row.get(COL_STATUS, ""),
            "roadmap_quarter":    row.get(COL_QUARTER, ""),
            "notes":              row.get(COL_NOTES, ""),
            "extraction_timestamp": ts,
            "source_system":      "SharePoint",
            "function_runtime":   "aws_lambda",
        }
        events.append({k: v for k, v in event.items() if v})
    print(f"  Created {len(events)} events")
    return events


def send_to_splunk_hec(events: list, hec_url: str, hec_token: str,
                       index_name: str, batch_size: int = 100) -> tuple:
    print(f"Sending {len(events)} events to Splunk HEC -> {index_name}")
    headers = {"Authorization": f"Splunk {hec_token}", "Content-Type": "application/json"}
    sent = failed = 0
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        payload = "\n".join(json.dumps({
            "time": int(time.time()), "host": "aws-lambda",
            "source": "sharepoint_api", "sourcetype": "sharepoint:compliance",
            "index": index_name, "event": e,
        }) for e in batch)
        try:
            resp = requests.post(hec_url, headers=headers, data=payload, verify=True, timeout=30)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                sent += len(batch)
            else:
                failed += len(batch)
                print(f"  Batch {i // batch_size + 1}: {resp.status_code} {resp.text[:100]}")
        except Exception as exc:
            failed += len(batch)
            print(f"  Batch {i // batch_size + 1}: {exc}")
    print(f"  HEC total: {sent} sent, {failed} failed")
    return sent, failed


# ---------------------------------------------------------------------------
# S3 daily snapshot storage
# ---------------------------------------------------------------------------
def upload_daily_snapshot(norm_df: pd.DataFrame, bucket: str, run_date: datetime) -> str:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = (
        f"compliance-runs/year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"compliance.csv"
    )
    s3.put_object(Bucket=bucket, Key=key,
                  Body=norm_df.to_csv(index=False).encode(), ContentType="text/csv")
    print(f"  Daily snapshot saved: s3://{bucket}/{key}")
    return key


def load_previous_snapshot(bucket: str) -> Optional[pd.DataFrame]:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        obj = s3.get_object(Bucket=bucket, Key="latest/compliance_latest.csv")
        df = pd.read_csv(io.BytesIO(obj["Body"].read()), keep_default_na=False)
        print(f"  Loaded previous snapshot: {len(df)} rows")
        return df
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "NoSuchBucket"):
            print("  No previous snapshot — first run, skipping change detection")
            return None
        raise


def update_latest_snapshot(norm_df: pd.DataFrame, bucket: str) -> None:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.put_object(Bucket=bucket, Key="latest/compliance_latest.csv",
                  Body=norm_df.to_csv(index=False).encode(), ContentType="text/csv")
    print("  Latest snapshot updated")


# ---------------------------------------------------------------------------
# Change detection (operates on normalized DataFrames)
# ---------------------------------------------------------------------------
def _build_status_map(norm_df: pd.DataFrame) -> dict:
    """
    Returns {change_key: (status, quarter)} from a normalized DataFrame.
    change_key = "Product|Feature|Infrastructure|Certification"
    """
    mapping = {}
    for _, row in norm_df.iterrows():
        key = "|".join([
            str(row.get(COL_PRODUCT, "")).strip(),
            str(row.get(COL_FEATURE,  "")).strip(),
            str(row.get(COL_INFRA,    "")).strip(),
            str(row.get(COL_CERT,     "")).strip(),
        ])
        mapping[key] = (
            str(row.get(COL_STATUS,  "")).strip(),
            str(row.get(COL_QUARTER, "")).strip(),
        )
    return mapping


def detect_status_changes(prev_df: pd.DataFrame, curr_df: pd.DataFrame,
                           run_date: datetime) -> list:
    prev_map = _build_status_map(prev_df)
    curr_map = _build_status_map(curr_df)
    detected_at = run_date.isoformat()
    date_str    = run_date.strftime("%Y-%m-%d")

    changes = []
    for key, (curr_status, curr_q) in curr_map.items():
        if key not in prev_map:
            continue
        prev_status, prev_q = prev_map[key]
        if prev_status == curr_status:
            continue

        parts = key.split("|")
        product = parts[0] if len(parts) > 0 else ""
        feature = parts[1] if len(parts) > 1 else ""
        infra   = parts[2] if len(parts) > 2 else ""
        cert    = parts[3] if len(parts) > 3 else ""

        changes.append({
            "item_key":            key,
            "detected_date":       date_str,
            "product":             product,
            "feature":             feature,
            "infrastructure":      infra,
            "certification":       cert,
            "from_status":         prev_status,
            "from_quarter":        prev_q,
            "to_status":           curr_status,
            "to_quarter":          curr_q,
            "detected_at":         detected_at,
            "is_roadmap_completion": (prev_status == STATUS_ON_ROADMAP
                                      and curr_status == STATUS_COMPLIANT),
        })

    completions = sum(1 for c in changes if c["is_roadmap_completion"])
    print(f"  {len(changes)} status changes ({completions} roadmap -> compliant)")
    return changes


def save_changes_to_dynamodb(changes: list, table_name: str) -> None:
    if not changes:
        return
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = ddb.Table(table_name)
    with table.batch_writer() as batch:
        for change in changes:
            item = {k: v for k, v in change.items() if v != "" and v is not None}
            batch.put_item(Item=item)
    print(f"  {len(changes)} change records saved to DynamoDB ({table_name})")


# ---------------------------------------------------------------------------
# Achievement history (On Roadmap -> Compliant transitions)
# ---------------------------------------------------------------------------
def _extract_achievement(change: dict) -> dict:
    return {
        "achievement_key":        f"{change['product']}|{change['feature']}|{change['certification']}",
        "achieved_date":          change["detected_date"],
        "product":                change["product"],
        "feature":                change["feature"],
        "infrastructure":         change["infrastructure"],
        "certification":          change["certification"],
        "original_expected_date": change["from_quarter"],
        "achieved_at":            change["detected_at"],
    }


def save_achievements_to_dynamodb(achievements: list, table_name: str) -> None:
    if not achievements:
        return
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = ddb.Table(table_name)
    with table.batch_writer() as batch:
        for rec in achievements:
            item = {k: v for k, v in rec.items() if v != "" and v is not None}
            batch.put_item(Item=item)
    print(f"  {len(achievements)} achievement records saved to DynamoDB ({table_name})")


def save_achievements_to_s3(achievements: list, bucket: str, run_date: datetime) -> Optional[str]:
    if not achievements:
        return None
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = (
        f"achievement-history/year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"achievements.csv"
    )
    fields = ["product", "feature", "infrastructure", "certification",
              "original_expected_date", "achieved_date", "achieved_at"]
    rows = [",".join(fields)]
    for rec in achievements:
        rows.append(",".join(f'"{rec.get(f, "")}"' for f in fields))
    s3.put_object(Bucket=bucket, Key=key,
                  Body="\n".join(rows).encode(), ContentType="text/csv")
    print(f"  Achievement history saved: s3://{bucket}/{key}")
    return key


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    run_date = datetime.now(timezone.utc)
    print("=" * 70)
    print("SharePoint -> Splunk Integration - AWS Lambda")
    print(f"Started: {run_date.isoformat()}")
    print("=" * 70)

    try:
        # 1. Secrets
        print("\n[1/6] Retrieving secrets...")
        client_id     = get_secret(f"{SECRET_PREFIX}-client-id")
        client_secret = get_secret(f"{SECRET_PREFIX}-client-secret")
        tenant_id     = get_secret(f"{SECRET_PREFIX}-tenant-id")
        hec_token     = get_secret(f"{SECRET_PREFIX}-hec-token")
        hec_url       = get_secret(f"{SECRET_PREFIX}-hec-url")
        index_name    = get_secret(f"{SECRET_PREFIX}-index-name")
        print("  All secrets retrieved")

        # 2. SharePoint -> raw wide DataFrame
        print("\n[2/6] Extracting SharePoint data...")
        token   = get_access_token(client_id, client_secret, tenant_id)
        site_id = get_site_id(token, SHAREPOINT_SITE_PATH)
        raw_df  = get_worksheet_data(token, site_id, FILE_ID, WORKSHEET_NAME)

        # 3. Normalize to dashboard-compatible 11-column format
        print("\n[3/6] Normalizing to dashboard format...")
        norm_df = normalize_to_dashboard_format(raw_df)

        # 4. S3 snapshot + change detection
        s3_key = None
        changes_detected = 0
        roadmap_completions = 0

        if S3_DATA_BUCKET:
            print("\n[4/6] Storing snapshot & detecting changes...")
            try:
                prev_df = load_previous_snapshot(S3_DATA_BUCKET)
                s3_key  = upload_daily_snapshot(norm_df, S3_DATA_BUCKET, run_date)

                if prev_df is not None:
                    changes = detect_status_changes(prev_df, norm_df, run_date)
                    changes_detected = len(changes)
                    save_changes_to_dynamodb(changes, DYNAMODB_CHANGES_TABLE)

                    achievements = [_extract_achievement(c) for c in changes
                                    if c["is_roadmap_completion"]]
                    roadmap_completions = len(achievements)
                    if achievements:
                        save_achievements_to_dynamodb(achievements, ACHIEVEMENTS_TABLE)
                        save_achievements_to_s3(achievements, S3_DATA_BUCKET, run_date)

                update_latest_snapshot(norm_df, S3_DATA_BUCKET)
            except Exception as exc:
                print(f"  S3/DynamoDB step failed (non-fatal): {exc}")
        else:
            print("\n[4/6] S3_DATA_BUCKET not configured - skipping snapshot & change detection")

        # 5. Transform normalized records to Splunk events
        print("\n[5/6] Transforming data...")
        events = transform_to_events(norm_df)

        # 6. Send to Splunk
        print("\n[6/6] Sending to Splunk HEC...")
        sent, failed_count = send_to_splunk_hec(events, hec_url, hec_token, index_name)

        duration = (datetime.now(timezone.utc) - run_date).total_seconds()
        summary = {
            "status":           "success",
            "execution_time":   run_date.isoformat(),
            "duration_seconds": round(duration, 2),
            "sharepoint": {
                "site":           SHAREPOINT_SITE_PATH,
                "worksheet":      WORKSHEET_NAME,
                "rows_extracted": len(raw_df),
            },
            "normalization": {
                "records":        len(norm_df),
                "compliant":      int((norm_df[COL_STATUS] == STATUS_COMPLIANT).sum()),
                "on_roadmap":     int((norm_df[COL_STATUS] == STATUS_ON_ROADMAP).sum()),
                "not_compliant":  int((norm_df[COL_STATUS] == STATUS_NOT_COMPLIANT).sum()),
                "not_applicable": int((norm_df[COL_STATUS] == STATUS_NA).sum()),
            },
            "s3": {
                "bucket":              S3_DATA_BUCKET,
                "key":                 s3_key,
                "changes_detected":    changes_detected,
                "roadmap_completions": roadmap_completions,
            },
            "splunk": {
                "events_created": len(events),
                "events_sent":    sent,
                "events_failed":  failed_count,
                "index":          index_name,
            },
        }
        print(f"\nDone: {sent}/{len(events)} events in {duration:.1f}s")
        return {"statusCode": 200, "body": json.dumps(summary)}

    except Exception as exc:
        duration = (datetime.now(timezone.utc) - run_date).total_seconds()
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error", "error": str(exc),
                "error_type": type(exc).__name__,
                "duration_seconds": round(duration, 2),
            }),
        }
