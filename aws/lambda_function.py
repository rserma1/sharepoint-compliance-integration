"""
AWS Lambda - SharePoint to Splunk HEC Integration
Extracts compliance data from SharePoint, sends to Splunk HEC,
stores daily snapshots to S3 (date-partitioned), and detects
status changes (esp. On Roadmap -> Compliant) in DynamoDB.
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
FILE_ID = "F07872BA-6EA5-40D0-A837-4A6505B4F336"
WORKSHEET_NAME = "Compliance Inventory"
SECRET_PREFIX = os.environ.get("SECRET_PREFIX", "sharepoint-compliance")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_DATA_BUCKET = os.environ.get("S3_DATA_BUCKET", "")
DYNAMODB_CHANGES_TABLE = os.environ.get("DYNAMODB_CHANGES_TABLE", "sharepoint-compliance-changes")
ACHIEVEMENTS_TABLE = os.environ.get("ACHIEVEMENTS_TABLE", "sharepoint-compliance-achievements")
# First N columns are entity identifiers (Product, Feature, etc.); rest are cert status columns
N_ENTITY_COLS = int(os.environ.get("N_ENTITY_COLS", "5"))
# Column names for achievement record fields (matched case-insensitively against the Excel headers)
PRODUCT_COL = os.environ.get("PRODUCT_COL", "Product")
FEATURE_COL = os.environ.get("FEATURE_COL", "Feature")
INFRA_COL   = os.environ.get("INFRA_COL", "Infrastructure")

_QUARTER_RE = re.compile(r"Q[1-4]FY\d{2}", re.IGNORECASE)
_COMPLIANT_VALS = {"✓", "✔", "yes", "compliant", "done", "complete", "completed"}
_NA_VALS = {"not applicable", "n/a", "na", ""}


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
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(token_url, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }, timeout=30)
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


def get_worksheet_data(access_token: str, site_id: str, file_id: str, worksheet_name: str) -> pd.DataFrame:
    print(f"Reading worksheet: {worksheet_name}")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/items/{file_id}/workbook/worksheets('{worksheet_name}')/usedRange"
    )
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()

    values = resp.json().get("values", [])
    if len(values) < 4:
        raise ValueError(f"Insufficient data in worksheet (got {len(values)} rows)")

    # Row 0-1: category/subcategory headers  Row 2: column names  Row 3+: data
    row0, row1, row2 = values[0], values[1], values[2]

    column_names = []
    for i in range(len(row2)):
        col = str(row2[i]).strip() if row2[i] else ""
        if i < len(row0) and row0[i] and str(row0[i]).strip():
            cat = str(row0[i]).strip()
            if cat not in col:
                col = f"{cat}_{col}" if col else cat
        if i < len(row1) and row1[i] and str(row1[i]).strip():
            sub = str(row1[i]).strip()
            if sub not in col:
                col = f"{col}_{sub}" if col else sub
        column_names.append(col or f"Column_{i}")

    df = pd.DataFrame(values[3:], columns=column_names)
    print(f"  Retrieved {len(df)} rows, {len(df.columns)} columns")
    return df


# ---------------------------------------------------------------------------
# Transform (for Splunk events)
# ---------------------------------------------------------------------------
def transform_to_events(df: pd.DataFrame, worksheet_name: str) -> list:
    print(f"Transforming {len(df)} rows to Splunk events...")
    ts = datetime.now(timezone.utc).isoformat()
    events = []
    for _, row in df.iterrows():
        event = {}
        for col, val in row.items():
            if val and str(val).strip():
                clean = (
                    col.replace(" ", "_").replace("/", "_")
                       .replace("-", "_").replace("(", "").replace(")", "")
                )
                event[clean] = str(val).strip()
        event["extraction_timestamp"] = ts
        event["source_system"] = "SharePoint"
        event["worksheet"] = worksheet_name
        event["function_runtime"] = "aws_lambda"
        events.append(event)
    print(f"  Created {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# Splunk HEC
# ---------------------------------------------------------------------------
def send_to_splunk_hec(events: list, hec_url: str, hec_token: str,
                        index_name: str, batch_size: int = 100) -> tuple:
    print(f"Sending {len(events)} events to Splunk HEC -> {index_name}")
    headers = {
        "Authorization": f"Splunk {hec_token}",
        "Content-Type": "application/json",
    }
    sent = failed = 0
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        hec_batch = [
            {
                "time": int(time.time()),
                "host": "aws-lambda",
                "source": "sharepoint_api",
                "sourcetype": "sharepoint:compliance",
                "index": index_name,
                "event": e,
            }
            for e in batch
        ]
        payload = "\n".join(json.dumps(e) for e in hec_batch)
        try:
            resp = requests.post(hec_url, headers=headers, data=payload,
                                  verify=True, timeout=30)
            if resp.status_code == 200 and resp.json().get("code") == 0:
                sent += len(batch)
                print(f"  Batch {i // batch_size + 1}: {len(batch)} events sent")
            else:
                failed += len(batch)
                print(f"  Batch {i // batch_size + 1}: {resp.status_code} {resp.text}")
        except Exception as exc:
            failed += len(batch)
            print(f"  Batch {i // batch_size + 1}: {exc}")
    print(f"  HEC total: {sent} sent, {failed} failed")
    return sent, failed


# ---------------------------------------------------------------------------
# S3 daily snapshot storage
# ---------------------------------------------------------------------------
def upload_daily_snapshot(df: pd.DataFrame, bucket: str, run_date: datetime) -> str:
    """Save today's full dataset to S3 with Hive-style date partitioning."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = (
        f"compliance-runs/year={run_date.strftime('%Y')}/"
        f"month={run_date.strftime('%m')}/"
        f"day={run_date.strftime('%d')}/"
        f"compliance.csv"
    )
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=df.to_csv(index=False).encode(),
        ContentType="text/csv",
    )
    print(f"  Daily snapshot saved: s3://{bucket}/{key}")
    return key


def load_previous_snapshot(bucket: str) -> Optional[pd.DataFrame]:
    """Load the latest snapshot CSV for change comparison. Returns None on first run."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        obj = s3.get_object(Bucket=bucket, Key="latest/compliance_latest.csv")
        df = pd.read_csv(io.BytesIO(obj["Body"].read()), keep_default_na=False)
        print(f"  Loaded previous snapshot: {len(df)} rows")
        return df
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NoSuchKey", "NoSuchBucket"):
            print("  No previous snapshot found - this is the first run, skipping change detection")
            return None
        raise


def update_latest_snapshot(df: pd.DataFrame, bucket: str) -> None:
    """Overwrite the latest snapshot so the next run can compare against it."""
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.put_object(
        Bucket=bucket,
        Key="latest/compliance_latest.csv",
        Body=df.to_csv(index=False).encode(),
        ContentType="text/csv",
    )
    print("  Latest snapshot updated for next comparison")


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------
def _parse_cell_status(value) -> tuple:
    """
    Parse a compliance cell value into (status, quarter).
    Status is one of: compliant | on_roadmap | not_applicable | other
    Quarter is the roadmap quarter string (e.g. Q1FY25) or empty string.
    """
    v = str(value).strip() if value else ""
    if v.lower() in _NA_VALS:
        return "not_applicable", ""
    if v.lower() in _COMPLIANT_VALS:
        return "compliant", ""
    m = _QUARTER_RE.search(v)
    if m:
        return "on_roadmap", m.group(0).upper()
    return "other", v


def _build_status_map(df: pd.DataFrame) -> dict:
    """
    Returns {(row_key, cert_col): (status, quarter)} for every
    (entity row, certification column) combination in the dataframe.
    row_key is the pipe-joined values of the first N_ENTITY_COLS columns.
    """
    if len(df.columns) <= N_ENTITY_COLS:
        return {}
    entity_cols = list(df.columns[:N_ENTITY_COLS])
    cert_cols = list(df.columns[N_ENTITY_COLS:])
    mapping = {}
    for _, row in df.iterrows():
        row_key = "|".join(str(row[c]).strip() for c in entity_cols)
        for col in cert_cols:
            mapping[(row_key, col)] = _parse_cell_status(row.get(col, ""))
    return mapping


def detect_status_changes(prev_df: pd.DataFrame, curr_df: pd.DataFrame,
                           run_date: datetime) -> list:
    """
    Compare previous and current snapshots column-by-column.
    Returns a list of change records. Each record includes:
      - item_key: unique identifier for this (row, certification) combination
      - detected_date: date string YYYY-MM-DD
      - from_status / to_status: previous and current parsed status
      - from_quarter / to_quarter: roadmap quarter if applicable
      - is_roadmap_completion: True when on_roadmap -> compliant (the key metric)
      - entity field values (product, feature, etc.)
    """
    prev_map = _build_status_map(prev_df)
    curr_map = _build_status_map(curr_df)
    entity_cols = list(curr_df.columns[:N_ENTITY_COLS])
    detected_at = run_date.isoformat()
    date_str = run_date.strftime("%Y-%m-%d")

    changes = []
    for (row_key, cert_col), (curr_status, curr_q) in curr_map.items():
        if (row_key, cert_col) not in prev_map:
            continue  # New row added since last run - not a status change
        prev_status, prev_q = prev_map[(row_key, cert_col)]
        if prev_status == curr_status:
            continue

        entity_vals = row_key.split("|")
        entity_dict = {
            entity_cols[i]: entity_vals[i]
            for i in range(min(len(entity_cols), len(entity_vals)))
        }
        changes.append({
            "item_key": f"{row_key}|{cert_col}",
            "detected_date": date_str,
            "cert_col": cert_col,
            "from_status": prev_status,
            "from_quarter": prev_q,
            "to_status": curr_status,
            "to_quarter": curr_q,
            "detected_at": detected_at,
            "is_roadmap_completion": prev_status == "on_roadmap" and curr_status == "compliant",
            **entity_dict,
        })

    completions = sum(1 for c in changes if c["is_roadmap_completion"])
    print(f"  {len(changes)} status changes detected ({completions} roadmap -> compliant)")
    return changes


def save_changes_to_dynamodb(changes: list, table_name: str) -> None:
    """Batch-write status change records to DynamoDB."""
    if not changes:
        return
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = ddb.Table(table_name)
    with table.batch_writer() as batch:
        for change in changes:
            # Filter out empty strings - DynamoDB rejects them for String attributes
            item = {k: v for k, v in change.items() if v != "" and v is not None}
            batch.put_item(Item=item)
    print(f"  {len(changes)} change records saved to DynamoDB ({table_name})")


# ---------------------------------------------------------------------------
# Achievement history  (On Roadmap -> Achieved/Compliant transitions only)
# ---------------------------------------------------------------------------
def _extract_achievement(change: dict) -> dict:
    """
    Build a clean achievement record from a roadmap-completion change.
    Fields: product, feature, infrastructure, certification, original_expected_date.
    """
    # Column name lookup is case-insensitive to handle Excel header variations
    col_lower = {k.lower(): k for k in change}
    def _get(col_name):
        return change.get(col_name) or change.get(col_lower.get(col_name.lower(), ""), "")

    product       = _get(PRODUCT_COL)
    feature       = _get(FEATURE_COL)
    infrastructure = _get(INFRA_COL)
    certification = change["cert_col"]

    return {
        "achievement_key":       f"{product}|{feature}|{certification}",
        "achieved_date":         change["detected_date"],
        "product":               product,
        "feature":               feature,
        "infrastructure":        infrastructure,
        "certification":         certification,
        "original_expected_date": change["from_quarter"],
        "achieved_at":           change["detected_at"],
    }


def save_achievements_to_dynamodb(achievements: list, table_name: str) -> None:
    """Batch-write achievement records to DynamoDB."""
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
    """
    Write today's achievements as a dated CSV under achievement-history/.
    Only creates the file if there is at least one achievement.
    """
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
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body="\n".join(rows).encode(),
        ContentType="text/csv",
    )
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
        print("\n[1/5] Retrieving secrets...")
        client_id     = get_secret(f"{SECRET_PREFIX}-client-id")
        client_secret = get_secret(f"{SECRET_PREFIX}-client-secret")
        tenant_id     = get_secret(f"{SECRET_PREFIX}-tenant-id")
        hec_token     = get_secret(f"{SECRET_PREFIX}-hec-token")
        hec_url       = get_secret(f"{SECRET_PREFIX}-hec-url")
        index_name    = get_secret(f"{SECRET_PREFIX}-index-name")
        print("  All secrets retrieved")

        # 2. SharePoint
        print("\n[2/5] Extracting SharePoint data...")
        token   = get_access_token(client_id, client_secret, tenant_id)
        site_id = get_site_id(token, SHAREPOINT_SITE_PATH)
        df      = get_worksheet_data(token, site_id, FILE_ID, WORKSHEET_NAME)

        # 3. S3 daily snapshot + change detection
        s3_key = None
        changes_detected = 0
        roadmap_completions = 0

        if S3_DATA_BUCKET:
            print("\n[3/5] Storing snapshot & detecting changes...")
            try:
                prev_df = load_previous_snapshot(S3_DATA_BUCKET)
                s3_key = upload_daily_snapshot(df, S3_DATA_BUCKET, run_date)

                if prev_df is not None:
                    changes = detect_status_changes(prev_df, df, run_date)
                    changes_detected = len(changes)
                    save_changes_to_dynamodb(changes, DYNAMODB_CHANGES_TABLE)

                    # Achievement history: on_roadmap -> compliant transitions only
                    achievements = [
                        _extract_achievement(c) for c in changes if c["is_roadmap_completion"]
                    ]
                    roadmap_completions = len(achievements)
                    if achievements:
                        save_achievements_to_dynamodb(achievements, ACHIEVEMENTS_TABLE)
                        save_achievements_to_s3(achievements, S3_DATA_BUCKET, run_date)

                update_latest_snapshot(df, S3_DATA_BUCKET)
            except Exception as exc:
                print(f"  S3/DynamoDB step failed (non-fatal): {exc}")
        else:
            print("\n[3/5] S3_DATA_BUCKET not configured - skipping snapshot & change detection")

        # 4. Transform for Splunk
        print("\n[4/5] Transforming data...")
        events = transform_to_events(df, WORKSHEET_NAME)

        # 5. Send to Splunk
        print("\n[5/5] Sending to Splunk HEC...")
        sent, failed_count = send_to_splunk_hec(events, hec_url, hec_token, index_name)

        duration = (datetime.now(timezone.utc) - run_date).total_seconds()
        summary = {
            "status": "success",
            "execution_time": run_date.isoformat(),
            "duration_seconds": round(duration, 2),
            "sharepoint": {
                "site": SHAREPOINT_SITE_PATH,
                "worksheet": WORKSHEET_NAME,
                "rows_extracted": len(df),
            },
            "s3": {
                "bucket": S3_DATA_BUCKET,
                "key": s3_key,
                "changes_detected": changes_detected,
                "roadmap_completions": roadmap_completions,
            },
            "splunk": {
                "events_created": len(events),
                "events_sent": sent,
                "events_failed": failed_count,
                "index": index_name,
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
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "duration_seconds": round(duration, 2),
            }),
        }
