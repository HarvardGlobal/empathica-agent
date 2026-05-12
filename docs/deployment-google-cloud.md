# Google Cloud Deployment Runbook

This project deploys a single ADK entrypoint: `empathica_orchestrator` (via `root_agent` in `agent.py`).

## Release branch rule

- Production deploys should originate from code merged into `main` through approved PR flow.
- Integration and staging validation should happen from `develop`.

## 1) Prerequisites

- Google Cloud project with billing enabled.
- Local CLIs installed:
  - `gcloud`
  - `adk`
- Authenticated user/service account with permissions for Vertex AI + GCS.

Minimum IAM for deployment principal:
- `roles/run.admin`
- `roles/iam.serviceAccountUser` (for runtime service account binding)
- `roles/artifactregistry.writer`
- `roles/cloudbuild.builds.editor`

## 2) Required environment variables

Set these before deploy:

```bash
export GOOGLE_CLOUD_PROJECT="<your-project-id>"
export GOOGLE_CLOUD_LOCATION="us-central1"
export STAGING_BUCKET="gs://<your-staging-bucket>"
export GOOGLE_GENAI_USE_VERTEXAI="true"
```

Optional:

```bash
export GOOGLE_GENAI_MODEL="gemini-2.5-flash"
export DRUG_KNOWLEDGE_API_URL="https://..."
export PATIENT_CONTEXT_API_URL="https://..."
export LITERATURE_RETRIEVAL_API_URL="https://..."
```

## 3) One-time cloud setup

```bash
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud services enable aiplatform.googleapis.com storage.googleapis.com
```

Create staging bucket if needed:

```bash
gsutil mb -l "$GOOGLE_CLOUD_LOCATION" "$STAGING_BUCKET"
```

## 4) Deploy

### Option A: Scripted (recommended)

```bash
./scripts/deploy_vertex.sh
```

### Option B: Manual

```bash
adk deploy . \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --region "$GOOGLE_CLOUD_LOCATION" \
  --staging-bucket "$STAGING_BUCKET"
```

## 4.1) Cloud Build trigger recommendations

- Create one trigger for `develop` (integration deploy target).
- Create one trigger for `main` (production deploy target).
- Require pull request merge before either trigger runs against shared environments.

## 5) Readiness checks before deploy

```bash
./.venv/bin/python -m pytest -q
```

Expected: tests pass.

## 6) Production notes

- Keep `GOOGLE_GENAI_USE_VERTEXAI=true` in production.
- Store secrets in Secret Manager, not `.env`.
- Tool APIs are optional; if unset, tools return safe stub responses.
- `literacy_adaptation` is a sub-agent, not a separately deployed service.

Example secret injection:

```bash
gcloud run services update empathica-agents \
  --region us-east4 \
  --update-secrets "API_TOKEN=projects/$GOOGLE_CLOUD_PROJECT/secrets/API_TOKEN:latest"
```

## 6.1) Post-deploy verification

```bash
gcloud run services describe empathica-agents \
  --region us-east4 \
  --format='value(status.url)'
```

```bash
gcloud run services describe empathica-agents \
  --region us-east4 \
  --format='yaml(spec.template.spec.containers[0].env)'
```

Confirm:
- service is serving a new revision
- `GOOGLE_CLOUD_LOCATION=us-central1`
- `GOOGLE_GENAI_MODEL` is set to an approved model

## 7) Troubleshooting

- `gcloud: command not found`: install Google Cloud SDK.
- `adk: command not found`: install ADK CLI in your active environment.
- Auth failures: run `gcloud auth application-default login`.
- Bucket errors: verify `STAGING_BUCKET` exists and IAM allows access.
