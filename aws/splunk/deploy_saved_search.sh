#!/usr/bin/env bash
# Deploy the "Refresh Product_Compliance_Infra_Data Lookup" saved search to Splunk Cloud.
#
# Usage:
#   ./deploy_saved_search.sh \
#     --host <your-stack>.splunkcloud.com \
#     --token <splunk-management-token> \
#     [--app search]
#
# The management token must have the capability to write saved searches
# in the target app (capability: edit_search_schedule_priority or admin).
#
# To generate a token in Splunk Cloud:
#   Settings > Tokens > New Token  (scope: saved searches, services.*)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SPLUNK_HOST=""
SPLUNK_TOKEN=""
SPLUNK_APP="search"
SPLUNK_PORT="8089"
SEARCH_NAME="Refresh Product_Compliance_Infra_Data Lookup"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)   SPLUNK_HOST="$2";  shift 2 ;;
    --token)  SPLUNK_TOKEN="$2"; shift 2 ;;
    --app)    SPLUNK_APP="$2";   shift 2 ;;
    --port)   SPLUNK_PORT="$2";  shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$SPLUNK_HOST" || -z "$SPLUNK_TOKEN" ]]; then
  echo "Usage: $0 --host <host> --token <token> [--app search] [--port 8089]"
  exit 1
fi

BASE_URL="https://${SPLUNK_HOST}:${SPLUNK_PORT}"
ENDPOINT="${BASE_URL}/servicesNS/nobody/${SPLUNK_APP}/saved/searches"
ENCODED_NAME="${SEARCH_NAME// /%20}"

echo "================================================================"
echo "Deploying saved search to Splunk Cloud"
echo "  Host    : $SPLUNK_HOST:$SPLUNK_PORT"
echo "  App     : $SPLUNK_APP"
echo "  Search  : $SEARCH_NAME"
echo "================================================================"

# ---------------------------------------------------------------------------
# Build SPL (same as savedsearches.conf, single-line for REST API)
# ---------------------------------------------------------------------------
SPL='index=pt_prod sourcetype="sharepoint:compliance" source="sharepoint_api" earliest=-48h'
SPL+=' | dedup product feature infrastructure certification sortby -_time'
SPL+=' | rename product as Product'
SPL+='         feature as Feature'
SPL+='         product_area as "Product Area"'
SPL+='         infrastructure as Infrastructure'
SPL+='         region as Region'
SPL+='         category as Category'
SPL+='         subcategory as Subcategory'
SPL+='         certification as Certification'
SPL+='         compliance_status as "Compliance Status"'
SPL+='         roadmap_quarter as "Roadmap Quarter"'
SPL+='         notes as "Additional Information (Notes)"'
SPL+=' | fillnull value="" "Roadmap Quarter" Category Subcategory "Additional Information (Notes)"'
SPL+=' | table Product Feature "Product Area" Infrastructure Region Category Subcategory'
SPL+='         Certification "Compliance Status" "Roadmap Quarter" "Additional Information (Notes)"'
SPL+=' | outputlookup Product_Compliance_Infra_Data.csv'

# ---------------------------------------------------------------------------
# Check if saved search already exists
# ---------------------------------------------------------------------------
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $SPLUNK_TOKEN" \
  "${ENDPOINT}/${ENCODED_NAME}" 2>/dev/null || echo "000")

if [[ "$HTTP_STATUS" == "200" ]]; then
  echo ""
  echo "Saved search already exists — updating..."
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $SPLUNK_TOKEN" \
    "${ENDPOINT}/${ENCODED_NAME}" \
    --data-urlencode "search=$SPL" \
    -d "cron_schedule=0 7 * * *" \
    -d "dispatch.earliest_time=-48h" \
    -d "dispatch.latest_time=now" \
    -d "enableSched=1" \
    -d "is_scheduled=1" \
    -d "description=Daily refresh of Product_Compliance_Infra_Data.csv from SharePoint HEC events")
else
  echo ""
  echo "Creating new saved search..."
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $SPLUNK_TOKEN" \
    "${ENDPOINT}" \
    --data-urlencode "name=$SEARCH_NAME" \
    --data-urlencode "search=$SPL" \
    -d "cron_schedule=0 7 * * *" \
    -d "dispatch.earliest_time=-48h" \
    -d "dispatch.latest_time=now" \
    -d "enableSched=1" \
    -d "is_scheduled=1" \
    -d "description=Daily refresh of Product_Compliance_Infra_Data.csv from SharePoint HEC events")
fi

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [[ "$HTTP_CODE" =~ ^2 ]]; then
  echo "  Done (HTTP $HTTP_CODE)"
else
  echo "  ERROR (HTTP $HTTP_CODE)"
  echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); [print('  ',m.get('text','')) for m in d.get('messages',[])]" 2>/dev/null || echo "$BODY"
  exit 1
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
echo ""
echo "Verifying saved search..."
VERIFY=$(curl -s \
  -H "Authorization: Bearer $SPLUNK_TOKEN" \
  -G "${ENDPOINT}/${ENCODED_NAME}" \
  -d "output_mode=json" | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('entry'):
    e = d['entry'][0]
    c = e['content']
    print(f\"  Name    : {e['name']}\")
    print(f\"  Enabled : {c.get('enabled', c.get('is_scheduled', '?'))}\")
    print(f\"  Schedule: {c.get('cron_schedule', '?')}\")
    print(f\"  Next run: {c.get('next_scheduled_time', 'unknown')}\")
else:
    print('  Could not parse response')
" 2>/dev/null || echo "  (verification parse error — check Splunk UI)")

echo "$VERIFY"

echo ""
echo "================================================================"
echo "Deployment complete!"
echo ""
echo "  The saved search will run daily at 07:00 UTC, one hour after"
echo "  the Lambda (06:00 UTC), refreshing:"
echo "    Product_Compliance_Infra_Data.csv"
echo ""
echo "  To run it immediately:"
echo "    curl -X POST \\"
echo "      -H 'Authorization: Bearer \$TOKEN' \\"
echo "      '${BASE_URL}/servicesNS/nobody/${SPLUNK_APP}/saved/searches/${ENCODED_NAME}/dispatch' \\"
echo "      -d 'dispatch.earliest_time=-48h' \\"
echo "      -d 'dispatch.latest_time=now'"
echo "================================================================"
