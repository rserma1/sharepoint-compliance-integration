"""
AWS Lambda - SharePoint Regional Availability to Splunk HEC Integration
Pulls the Regional Availability (Product) and Regional Availability (Feature)
worksheets from SharePoint, normalizes them to the rdmp_reg_aval.csv lookup
format, sends to Splunk HEC, stores dated S3 snapshots, and tracks changes
in DynamoDB.
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
SHAREPOINT_SITE_PATH  = "cisco.sharepoint.com:/sites/Splunk-Product-Compliance"
FILE_ID               = os.environ.get("RAC_FILE_ID", "F07872BA-6EA5-40D0-A837-4A6505B4F336")
PRODUCT_SHEET_NAME    = os.environ.get("RAC_PRODUCT_SHEET", "Regional Availability (Product)")
FEATURE_SHEET_NAME    = os.environ.get("RAC_FEATURE_SHEET", "Regional Availability (Feature)")
SECRET_PREFIX         = os.environ.get("SECRET_PREFIX", "sharepoint-compliance")
AWS_REGION            = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-east-1"))
S3_DATA_BUCKET        = os.environ.get("S3_DATA_BUCKET", "")
DYNAMODB_CHANGES_TABLE = os.environ.get("RAC_DYNAMODB_CHANGES_TABLE", "sharepoint-rac-changes")

# Output column names — must match rdmp_reg_aval.csv / dashboard expectations
COL_PRODUCT_NAME    = "Product_Name"
COL_FEATURE         = "Feature"
COL_PRODUCT_FEATURE = "Product_Feature"
COL_PRODUCT_AREA    = "Product_Area"
COL_LAUNCH_PHASE    = "Launch_Phase"
COL_STATUS          = "Status"
COL_TARGET          = "Target"
COL_REGION_LIST     = "regionList"
COL_HOSTING         = "Hosting_Solution"
COL_LAUNCH_TIER     = "Launch_Tier"
COL_KEY             = "Key"
COL_REGIONS_ALL     = "Regions_All"
COL_CELL_VALUE      = "Cell_Value"

OUTPUT_COLUMNS = [
    COL_PRODUCT_NAME, COL_FEATURE, COL_PRODUCT_FEATURE, COL_PRODUCT_AREA,
    COL_LAUNCH_PHASE, COL_STATUS, COL_TARGET, COL_REGION_LIST,
    COL_HOSTING, COL_LAUNCH_TIER, COL_KEY, COL_REGIONS_ALL, COL_CELL_VALUE,
]

# Phase name normalisation
_PHASE_MAP = {
    "GA":                      "General Availability",
    "General Availability":    "General Availability",
    "Beta":                    "Beta",
    "Alpha":                   "Alpha",
    "Controlled Availability": "Controlled Availability",
    "CA":                      "Controlled Availability",
}


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------
def get_secret(secret_id: str) -> str:
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=secret_id)
    return response["SecretString"]


# ---------------------------------------------------------------------------
# SharePoint / Graph API  (same helpers as compliance Lambda)
# ---------------------------------------------------------------------------
def get_access_token(client_id: str, client_secret: str, tenant_id: str) -> str:
    print("Getting SharePoint access token...")
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
            "scope":         "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("  Access token obtained")
    return token


def get_site_id(token: str, site_path: str) -> str:
    print(f"Getting site ID for: {site_path}")
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    site_id = resp.json()["id"]
    print(f"  Site ID: {site_id}")
    return site_id


def get_worksheet_values(token: str, site_id: str, file_id: str, sheet_name: str) -> list:
    """Return raw 2-D list of cell values for the given worksheet (usedRange)."""
    print(f"  Fetching worksheet: {sheet_name}")
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/items/{file_id}/workbook/worksheets/{sheet_name}/usedRange"
    )
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    resp.raise_for_status()
    values = resp.json().get("values", [])
    print(f"    {len(values)} rows returned")
    return values


# ---------------------------------------------------------------------------
# Cell / region helpers  (ported from build_lookup.py)
# ---------------------------------------------------------------------------
def parse_cell_value(cell_val) -> tuple:
    """Return (Launch_Phase, Status, Target) from a cell like 'GA: Available'."""
    if cell_val is None or str(cell_val).strip() == "":
        return None, None, None
    text = str(cell_val).strip()
    if ":" in text:
        phase_raw, rest = text.split(":", 1)
        rest = rest.strip()
    else:
        phase_raw = text
        rest = ""
    launch_phase = _PHASE_MAP.get(phase_raw.strip(), phase_raw.strip())
    if rest.lower() == "available" or rest.strip() == launch_phase:
        status, target = "Done", "Available"
    elif re.match(r"^Q\d", rest):
        status, target = "Upcoming", rest
    elif rest:
        status, target = "Upcoming", rest
    else:
        status, target = "Upcoming", "Unknown"
    return launch_phase, status, target


def hosting_solution(region_name: str) -> str:
    r = region_name.strip()
    if r.startswith("Victoria"):
        if "Azure" in r:
            return "Azure"
        if "GCP" in r:
            return "GCP"
        return "Victoria"
    if r.startswith("GCP"):
        return "GCP"
    if r.startswith("AWS"):
        return "AWS"
    return "Other"


def launch_tier(region_name: str) -> str:
    return "Victoria" if region_name.strip().startswith("Victoria") else "Classic"


def extract_product_from_feature(feature_name: str) -> str:
    m = re.search(r"\[(.+?)\]\s*(?:\(.*\))?\s*$", feature_name)
    if m:
        return m.group(1).strip()
    parts = re.findall(r"\[(.+?)\]", feature_name)
    return parts[-1].strip() if parts else ""


def feature_display(feature_name: str) -> str:
    m = re.match(r"^(.+?)\s*\[", feature_name)
    return m.group(1).strip() if m else feature_name.strip()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize_product_sheet(values: list) -> pd.DataFrame:
    """Wide product sheet → tall DataFrame (one row per product × region)."""
    if len(values) < 2:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    header = [str(c).strip() if c else "" for c in values[0]]
    region_cols = header[2:]   # skip Product Name, Product Area
    rows_out = []
    for raw_row in values[1:]:
        product_name = str(raw_row[0]).strip() if len(raw_row) > 0 and raw_row[0] else ""
        if not product_name:
            continue
        p_area = str(raw_row[1]).strip() if len(raw_row) > 1 and raw_row[1] else "Platform"
        for idx, region in enumerate(region_cols):
            cell_idx = idx + 2
            cell_val = raw_row[cell_idx] if cell_idx < len(raw_row) else None
            launch_phase, status, target = parse_cell_value(cell_val)
            if launch_phase is None:
                continue
            rows_out.append({
                COL_PRODUCT_NAME:    product_name,
                COL_FEATURE:         "",
                COL_PRODUCT_FEATURE: "",
                COL_PRODUCT_AREA:    p_area,
                COL_LAUNCH_PHASE:    launch_phase,
                COL_STATUS:          status,
                COL_TARGET:          target,
                COL_REGION_LIST:     region,
                COL_HOSTING:         hosting_solution(region),
                COL_LAUNCH_TIER:     launch_tier(region),
                COL_KEY:             f"{product_name}|{region}",
                COL_REGIONS_ALL:     region,
                COL_CELL_VALUE:      str(cell_val).strip(),
            })
    print(f"  Product sheet: {len(rows_out)} records")
    return pd.DataFrame(rows_out, columns=OUTPUT_COLUMNS)


def normalize_feature_sheet(values: list) -> pd.DataFrame:
    """Wide feature sheet → tall DataFrame (one row per feature × region)."""
    if len(values) < 2:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    header = [str(c).strip() if c else "" for c in values[0]]
    region_cols = header[2:]   # skip Feature Name, Product Area
    rows_out = []
    for raw_row in values[1:]:
        raw_feature = str(raw_row[0]).strip() if len(raw_row) > 0 and raw_row[0] else ""
        if not raw_feature:
            continue
        parent_product = extract_product_from_feature(raw_feature)
        feat = feature_display(raw_feature)
        p_area = str(raw_row[1]).strip() if len(raw_row) > 1 and raw_row[1] else "Platform"
        pf_label = f"{feat} [{parent_product}]" if parent_product else feat
        for idx, region in enumerate(region_cols):
            cell_idx = idx + 2
            cell_val = raw_row[cell_idx] if cell_idx < len(raw_row) else None
            launch_phase, status, target = parse_cell_value(cell_val)
            if launch_phase is None:
                continue
            rows_out.append({
                COL_PRODUCT_NAME:    parent_product,
                COL_FEATURE:         feat,
                COL_PRODUCT_FEATURE: pf_label,
                COL_PRODUCT_AREA:    p_area,
                COL_LAUNCH_PHASE:    launch_phase,
                COL_STATUS:          status,
                COL_TARGET:          target,
                COL_REGION_LIST:     region,
                COL_HOSTING:         hosting_solution(region),
                COL_LAUNCH_TIER:     launch_tier(region),
                COL_KEY:             f"{pf_label}|{region}",
                COL_REGIONS_ALL:     region,
                COL_CELL_VALUE:      str(cell_val).strip(),
            })
    print(f"  Feature sheet: {len(rows_out)} records")
    return pd.DataFrame(rows_out, columns=OUTPUT_COLUMNS)


# ---------------------------------------------------------------------------
# Splunk HEC events
# ---------------------------------------------------------------------------
def transform_to_events(df: pd.DataFrame) -> list:
    print(f"Transforming {len(df)} records to Splunk events...")
    ts = datetime.now(timezone.utc).isoformat()
    events = []
    for _, row in df.iterrows():
        event = {
            # lowercase snake_case for HEC — saved search renames to lookup schema
            "product_name":       row.get(COL_PRODUCT_NAME, ""),
            "feature":            row.get(COL_FEATURE, ""),
            "product_feature":    row.get(COL_PRODUCT_FEATURE, ""),
            "product_area":       row.get(COL_PRODUCT_AREA, ""),
            "launch_phase":       row.get(COL_LAUNCH_PHASE, ""),
            "status":             row.get(COL_STATUS, ""),
            "target":             row.get(COL_TARGET, ""),
            "region_list":        row.get(COL_REGION_LIST, ""),
            "hosting_solution":   row.get(COL_HOSTING, ""),
            "launch_tier":        row.get(COL_LAUNCH_TIER, ""),
            "key":                row.get(COL_KEY, ""),
            "regions_all":        row.get(COL_REGIONS_ALL, ""),
            "cell_value":         row.get(COL_CELL_VALUE, ""),
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
            "time":       int(time.time()),
            "host":       "aws-lambda",
            "source":     "sharepoint_api",
            "sourcetype": "sharepoint:regional_availability",
            "index":      index_name,
            "event":      e,
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
# S3 snapshots
# ---------------------------------------------------------------------------
def upload_daily_snapshot(df: pd.DataFrame, bucket: str, run_date: datetime) -> str:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = (
        f"rac-runs/year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"rac.csv"
    )
    s3.put_object(Bucket=bucket, Key=key,
                  Body=df.to_csv(index=False).encode(), ContentType="text/csv")
    print(f"  Daily snapshot saved: s3://{bucket}/{key}")
    return key


def load_previous_snapshot(bucket: str) -> Optional[pd.DataFrame]:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        obj = s3.get_object(Bucket=bucket, Key="latest/rac_latest.csv")
        df = pd.read_csv(io.BytesIO(obj["Body"].read()), keep_default_na=False)
        print(f"  Loaded previous snapshot: {len(df)} rows")
        return df
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "NoSuchBucket"):
            print("  No previous snapshot — first run, skipping change detection")
            return None
        raise


def update_latest_snapshot(df: pd.DataFrame, bucket: str) -> None:
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.put_object(Bucket=bucket, Key="latest/rac_latest.csv",
                  Body=df.to_csv(index=False).encode(), ContentType="text/csv")
    print("  Latest RAC snapshot updated")


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------
def _build_status_map(df: pd.DataFrame) -> dict:
    """key = Key column value  →  (Launch_Phase, Status, Target)"""
    mapping = {}
    for _, row in df.iterrows():
        k = str(row.get(COL_KEY, "")).strip()
        if k:
            mapping[k] = (
                str(row.get(COL_LAUNCH_PHASE, "")).strip(),
                str(row.get(COL_STATUS,       "")).strip(),
                str(row.get(COL_TARGET,        "")).strip(),
            )
    return mapping


def detect_status_changes(prev_df: pd.DataFrame, curr_df: pd.DataFrame,
                           run_date: datetime) -> list:
    prev_map = _build_status_map(prev_df)
    curr_map = _build_status_map(curr_df)
    date_str    = run_date.strftime("%Y-%m-%d")
    detected_at = run_date.isoformat()
    changes = []
    for key, (curr_phase, curr_status, curr_target) in curr_map.items():
        if key not in prev_map:
            continue
        prev_phase, prev_status, prev_target = prev_map[key]
        if prev_phase == curr_phase and prev_status == curr_status and prev_target == curr_target:
            continue
        parts = key.split("|")
        changes.append({
            "item_key":       key,
            "detected_date":  date_str,
            "entity":         parts[0] if parts else "",
            "region":         parts[1] if len(parts) > 1 else "",
            "from_phase":     prev_phase,
            "from_status":    prev_status,
            "from_target":    prev_target,
            "to_phase":       curr_phase,
            "to_status":      curr_status,
            "to_target":      curr_target,
            "detected_at":    detected_at,
        })
    print(f"  {len(changes)} RAC status changes detected")
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
# Lambda handler
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    run_date = datetime.now(timezone.utc)
    print("=" * 70)
    print("SharePoint Regional Availability -> Splunk Integration - AWS Lambda")
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

        # 2. SharePoint -> raw worksheet values
        print("\n[2/6] Extracting SharePoint data...")
        token   = get_access_token(client_id, client_secret, tenant_id)
        site_id = get_site_id(token, SHAREPOINT_SITE_PATH)
        product_values = get_worksheet_values(token, site_id, FILE_ID, PRODUCT_SHEET_NAME)
        feature_values = get_worksheet_values(token, site_id, FILE_ID, FEATURE_SHEET_NAME)

        # 3. Normalise both sheets → combined tall DataFrame
        print("\n[3/6] Normalising to rdmp_reg_aval format...")
        product_df = normalize_product_sheet(product_values)
        feature_df = normalize_feature_sheet(feature_values)
        norm_df    = pd.concat([product_df, feature_df], ignore_index=True)
        print(f"  Combined: {len(norm_df)} records "
              f"({len(product_df)} product, {len(feature_df)} feature)")

        # 4. S3 snapshot + change detection
        s3_key = None
        changes_detected = 0

        if S3_DATA_BUCKET:
            print("\n[4/6] Storing snapshot & detecting changes...")
            try:
                prev_df = load_previous_snapshot(S3_DATA_BUCKET)
                s3_key  = upload_daily_snapshot(norm_df, S3_DATA_BUCKET, run_date)
                if prev_df is not None:
                    changes = detect_status_changes(prev_df, norm_df, run_date)
                    changes_detected = len(changes)
                    save_changes_to_dynamodb(changes, DYNAMODB_CHANGES_TABLE)
                update_latest_snapshot(norm_df, S3_DATA_BUCKET)
            except Exception as exc:
                print(f"  S3/DynamoDB step failed (non-fatal): {exc}")
        else:
            print("\n[4/6] S3_DATA_BUCKET not configured — skipping snapshot & change detection")

        # 5. Transform to HEC events
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
                "site":                SHAREPOINT_SITE_PATH,
                "product_sheet":       PRODUCT_SHEET_NAME,
                "feature_sheet":       FEATURE_SHEET_NAME,
                "product_raw_rows":    len(product_values) - 1 if product_values else 0,
                "feature_raw_rows":    len(feature_values) - 1 if feature_values else 0,
            },
            "normalization": {
                "product_records": len(product_df),
                "feature_records": len(feature_df),
                "total_records":   len(norm_df),
            },
            "s3": {
                "bucket":           S3_DATA_BUCKET,
                "key":              s3_key,
                "changes_detected": changes_detected,
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
                "status":           "error",
                "error":            str(exc),
                "error_type":       type(exc).__name__,
                "duration_seconds": round(duration, 2),
            }),
        }
