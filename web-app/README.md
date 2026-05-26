# Web App Layer (Frontend + Backend)

This folder contains a basic application layer that sits in front of the private `empathica-agents` service.

- `frontend/` React app (user login, chat UI, onboarding upload UI)
- `backend/` Express API (auth + secure proxy to private Cloud Run endpoints)

## Why this exists

Your private medical agent should not be called directly from browser clients.
The backend in this folder:

1. Authenticates your app users
2. Maps a user to deterministic `user_id`
3. Calls private Cloud Run with service-account identity token

## Quick start

### 0) Start PostgreSQL

```bash
cd web-app
docker compose up -d
```

### 1) Backend

```bash
cd web-app/backend
npm install
cp .env.example .env
npm run dev
```

### 2) Frontend

```bash
cd web-app/frontend
npm install
cp .env.example .env
npm run dev
```

## Important

- This is a starter implementation.
- Replace demo auth/user storage before production.
- Keep Cloud Run private; do not expose `allUsers` in production.

## Production Connection Plan (Current Mode)

Current truth for this project:
- **AI Backend** (`empathica-agents`) runs in Google Cloud Run
- **Web Backend** (this folder) runs outside GCP (local/self-hosted)

1. Frontend calls only backend (`/auth`, `/api/chat`, `/api/onboarding/upload`)
2. Backend authenticates user with Postgres and resolves cloud mapping from `app_users.cloud_user_id`
3. Backend calls private `empathica-agents` using runtime service account identity token
4. `empathica-agents` trusts only the service account used by your Web Backend (`roles/run.invoker`)

### Current Mode Checklist (Web Backend outside GCP)

1) Keep `empathica-agents` private:

```bash
gcloud run services get-iam-policy empathica-agents \
  --region us-east4 \
  --format='yaml(bindings)'
```

2) Grant invoker to your Web Backend service account:

```bash
gcloud run services add-iam-policy-binding empathica-agents \
  --region us-east4 \
  --member='serviceAccount:<web-backend-invoker-sa>@<project>.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

3) Configure Web Backend runtime with:
- `GOOGLE_APPLICATION_CREDENTIALS=<absolute path to SA key json>`
- `CLOUD_RUN_SERVICE_URL=https://empathica-agents-...`
- Postgres/JWT/CORS env vars

4) Remove temporary user-based invoker access when SA is working:

```bash
gcloud run services remove-iam-policy-binding empathica-agents \
  --region us-east4 \
  --member='user:admin@dcinetwork.org' \
  --role='roles/run.invoker'
```

5) Ensure demo user mappings exist:

```bash
psql "$DATABASE_URL" -f web-app/scripts/bootstrap_default_mappings.sql
```

6) Run one-command local validation:

```bash
bash web-app/scripts/validate_local_e2e.sh
```

This validates:
- backend health
- Postgres user mappings
- Mary login + chat identity
- Emily login + chat identity

## Optional Future Mode (Web Backend on Cloud Run)

If you later move Web Backend to GCP, deployment artifacts are included:
- `web-app/backend/Dockerfile`
- `web-app/backend/cloudbuild.yaml`
- `web-app/scripts/deploy_backend_cloud_run.sh`
