#!/usr/bin/env bash
set -euo pipefail

# Empathica deploy helper for Vertex AI via ADK.
# Usage:
#   ./scripts/deploy_vertex.sh
# Required env vars:
#   GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, STAGING_BUCKET

required_vars=(GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION STAGING_BUCKET)
for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: Missing required env var: $v" >&2
    exit 1
  fi
done

if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERROR: gcloud CLI is not installed or not in PATH" >&2
  exit 1
fi

if ! command -v adk >/dev/null 2>&1; then
  echo "ERROR: adk CLI is not installed or not in PATH" >&2
  exit 1
fi

echo "==> Setting gcloud project: ${GOOGLE_CLOUD_PROJECT}"
gcloud config set project "${GOOGLE_CLOUD_PROJECT}" >/dev/null

echo "==> Enabling required services"
gcloud services enable aiplatform.googleapis.com storage.googleapis.com >/dev/null

echo "==> Verifying ADC auth"
gcloud auth application-default print-access-token >/dev/null

echo "==> Deploying ADK app (root_agent from agent.py)"
adk deploy . \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${GOOGLE_CLOUD_LOCATION}" \
  --staging-bucket "${STAGING_BUCKET}"

echo "==> Deploy complete"
