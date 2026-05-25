#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-dci-chatbot-476416}"
REGION="${REGION:-us-east4}"
BACKEND_SERVICE="${BACKEND_SERVICE:-empathica-web-backend}"
AGENTS_SERVICE="${AGENTS_SERVICE:-empathica-agents}"
BACKEND_SA="${BACKEND_SA:-empathica-web-backend-runtime@${PROJECT_ID}.iam.gserviceaccount.com}"
DB_URL="${DATABASE_URL:?DATABASE_URL is required}"
JWT_SECRET="${APP_JWT_SECRET:?APP_JWT_SECRET is required}"
CLOUD_RUN_SERVICE_URL="${CLOUD_RUN_SERVICE_URL:?CLOUD_RUN_SERVICE_URL is required}"
CORS_ORIGIN="${CORS_ORIGIN:?CORS_ORIGIN is required}"


echo "[1/6] Project ${PROJECT_ID}, region ${REGION}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "[2/6] Enable required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com >/dev/null

echo "[3/6] Ensure backend runtime service account exists"
if ! gcloud iam service-accounts describe "${BACKEND_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${BACKEND_SA%@*}" --display-name="Empathica Web Backend Runtime"
fi

echo "[4/6] Build backend image"
gcloud builds submit --config web-app/backend/cloudbuild.yaml .
IMAGE="us-east4-docker.pkg.dev/${PROJECT_ID}/web-app/empathica-web-backend:$(git rev-parse HEAD)"

echo "[5/6] Deploy backend Cloud Run service"
gcloud run deploy "${BACKEND_SERVICE}" \
  --region "${REGION}" \
  --image "${IMAGE}" \
  --service-account "${BACKEND_SA}" \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=${DB_URL},APP_JWT_SECRET=${JWT_SECRET},CLOUD_RUN_SERVICE_URL=${CLOUD_RUN_SERVICE_URL},CORS_ORIGIN=${CORS_ORIGIN},PGSSLMODE=require,PG_SSL_REJECT_UNAUTHORIZED=true"

echo "[6/6] Allow backend SA to invoke agents service"
gcloud run services add-iam-policy-binding "${AGENTS_SERVICE}" \
  --region "${REGION}" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/run.invoker"

echo "Done. Backend URL:"
gcloud run services describe "${BACKEND_SERVICE}" --region "${REGION}" --format='value(status.url)'
