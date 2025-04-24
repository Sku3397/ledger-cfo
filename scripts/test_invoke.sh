#!/usr/bin/env bash
set -e

# Get the service URL
SERVICE_URL=$(gcloud run services describe ledger --platform managed --region us-east4 --format="value(status.url)")
echo "Service URL: $SERVICE_URL"

# Get identity token for authentication
TOKEN=$(gcloud auth print-identity-token)

# Test the root path endpoint
echo "Testing POST to /"
ROOT_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVICE_URL/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"run_audit"}')

echo "Root endpoint response code: $ROOT_RESPONSE"
if [ "$ROOT_RESPONSE" -ne 200 ]; then
  echo "ERROR: POST to / failed with status $ROOT_RESPONSE"
  ROOT_SUCCESS=false
else
  echo "SUCCESS: POST to / returned 200 OK"
  ROOT_SUCCESS=true
fi

# Test the /trigger endpoint
echo "Testing POST to /trigger"
TRIGGER_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVICE_URL/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"run_audit"}')

echo "Trigger endpoint response code: $TRIGGER_RESPONSE"
if [ "$TRIGGER_RESPONSE" -ne 200 ]; then
  echo "ERROR: POST to /trigger failed with status $TRIGGER_RESPONSE"
  TRIGGER_SUCCESS=false
else
  echo "SUCCESS: POST to /trigger returned 200 OK"
  TRIGGER_SUCCESS=true
fi

# Tail logs for a few seconds to verify
echo "Tailing logs for 5 seconds..."
timeout 5 gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ledger" --limit=10 --format="table(timestamp,severity,textPayload)" || true

# Final status
if [ "$ROOT_SUCCESS" = true ] || [ "$TRIGGER_SUCCESS" = true ]; then
  echo "[OK] Test completed successfully - at least one endpoint is working"
  exit 0
else
  echo "[FAIL] Test failed - both endpoints returned errors"
  exit 1
fi 