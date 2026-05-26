#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:55432/empathica_web}"

MARY_EMAIL="${MARY_EMAIL:-mary@dci.com}"
MARY_PASSWORD_DEFAULT="${MARY_PASSWORD:-12345678}"
EMILY_EMAIL="${EMILY_EMAIL:-emily@dci.com}"
EMILY_PASSWORD_DEFAULT="${EMILY_PASSWORD:-12345678}"

jq_bin="$(command -v jq || true)"
if [[ -z "$jq_bin" ]]; then
  echo "ERROR: jq is required" >&2
  exit 1
fi

echo "[1/6] Health check"
curl -fsS "$BASE_URL/healthz" | jq .

echo "[2/6] Verify user mappings in Postgres"
psql "$DATABASE_URL" -At -F $'\t' -c "SELECT email, user_id, cloud_user_id, tenant, status FROM app_users WHERE email IN ('$MARY_EMAIL','$EMILY_EMAIL') ORDER BY email;"

echo "[3/6] Login Mary"
MARY_TOKEN="$(curl -fsS -X POST "$BASE_URL/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$MARY_EMAIL\",\"password\":\"$MARY_PASSWORD_DEFAULT\"}" | jq -r '.token')"
[[ "$MARY_TOKEN" != "null" && -n "$MARY_TOKEN" ]]

echo "[4/6] Mary chat"
MARY_RESP="$(curl -fsS -X POST "$BASE_URL/api/chat" -H "Authorization: Bearer $MARY_TOKEN" -H 'Content-Type: application/json' -d '{"message":"Is ibuprofen safe with my current treatment?"}')"
echo "$MARY_RESP" | jq '{thread_id, identity: .debug.identity, has_answer: (.answer|length>0)}'

echo "[5/6] Login Emily"
EMILY_TOKEN="$(curl -fsS -X POST "$BASE_URL/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"$EMILY_EMAIL\",\"password\":\"$EMILY_PASSWORD_DEFAULT\"}" | jq -r '.token')"
[[ "$EMILY_TOKEN" != "null" && -n "$EMILY_TOKEN" ]]

echo "[6/6] Emily chat"
EMILY_RESP="$(curl -fsS -X POST "$BASE_URL/api/chat" -H "Authorization: Bearer $EMILY_TOKEN" -H 'Content-Type: application/json' -d '{"message":"Can you summarize my medications?"}')"
echo "$EMILY_RESP" | jq '{thread_id, identity: .debug.identity, has_answer: (.answer|length>0)}'

echo "\nValidation complete. Confirm the identity.user_id differs correctly between Mary and Emily."
