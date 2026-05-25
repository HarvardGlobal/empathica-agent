#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   GOOGLE_APPLICATION_CREDENTIALS=/abs/path/key.json \
#   SERVICE_URL=https://<cloud-run-url> \
#   scripts/test_onboarding_local.sh
#
# Optional overrides:
#   USER_ID=000-002
#   TENANT=default
#   STATUS=active
#   FHIR_FILE=persona-data/mary-rodriguez-johnson/structured_fhir_mary.json
#   DOC_FILE=persona-data/mary-rodriguez-johnson/unstructured_mary.md

USER_ID="${USER_ID:-000-002}"
TENANT="${TENANT:-default}"
STATUS="${STATUS:-active}"
FHIR_FILE="${FHIR_FILE:-persona-data/mary-rodriguez-johnson/structured_fhir_mary.json}"
DOC_FILE="${DOC_FILE:-persona-data/mary-rodriguez-johnson/unstructured_mary.md}"

if [[ -z "${SERVICE_URL:-}" ]]; then
  echo "ERROR: SERVICE_URL is required."
  exit 1
fi

if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS is required."
  exit 1
fi

if [[ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
  echo "ERROR: GOOGLE_APPLICATION_CREDENTIALS file not found: $GOOGLE_APPLICATION_CREDENTIALS"
  exit 1
fi

if [[ ! -f "$FHIR_FILE" ]]; then
  echo "ERROR: FHIR file not found: $FHIR_FILE"
  exit 1
fi

if [[ ! -f "$DOC_FILE" ]]; then
  echo "ERROR: Unstructured file not found: $DOC_FILE"
  exit 1
fi

TOKEN="$(python3 - <<PY
import google.auth.transport.requests
from google.oauth2 import id_token
req = google.auth.transport.requests.Request()
aud = "${SERVICE_URL}"
print(id_token.fetch_id_token(req, aud))
PY
)"

echo "== Health check =="
curl -sS -X GET "${SERVICE_URL}/healthz" \
  -H "Authorization: Bearer ${TOKEN}" | jq .

echo
echo "== Onboarding upload =="
curl -sS -X POST "${SERVICE_URL}/onboarding/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "user_id=${USER_ID}" \
  -F "tenant=${TENANT}" \
  -F "status=${STATUS}" \
  -F "structured_fhir_file=@${FHIR_FILE};type=application/json" \
  -F "unstructured_file=@${DOC_FILE};type=text/markdown" | jq .

echo
echo "== Chat test =="
curl -sS -X POST "${SERVICE_URL}/chat" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\":\"${USER_ID}\",
    \"message\":\"Is ibuprofen safe with my current treatment?\",
    \"literacy_level\":\"medium\",
    \"empathy_level\":\"medium\"
  }" | jq .

