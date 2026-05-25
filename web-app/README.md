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

## Production Connection Plan (Frontend repo -> Backend Cloud Run -> Agents Cloud Run)

1. Frontend calls only backend (`/auth`, `/api/chat`, `/api/onboarding/upload`)
2. Backend authenticates user with Postgres and resolves cloud mapping from `app_users.cloud_user_id`
3. Backend calls private `empathica-agents` using runtime service account identity token
4. `empathica-agents` trusts only backend runtime service account (`roles/run.invoker`)

### Deploy backend to Cloud Run

From repository root:

```bash
export PROJECT_ID=dci-chatbot-476416
export REGION=us-east4
export CLOUD_RUN_SERVICE_URL=https://empathica-agents-ruokekq5ya-uk.a.run.app
export CORS_ORIGIN=https://<your-frontend-domain>
export DATABASE_URL='postgresql://...'
export APP_JWT_SECRET='<strong-random-secret>'

bash web-app/scripts/deploy_backend_cloud_run.sh
```

### Lock down agent service invokers

After backend deployment, keep only backend service account as invoker:

```bash
gcloud run services get-iam-policy empathica-agents \
  --region us-east4 \
  --format='yaml(bindings)'

# remove temporary user-based access if present
gcloud run services remove-iam-policy-binding empathica-agents \
  --region us-east4 \
  --member='user:admin@dcinetwork.org' \
  --role='roles/run.invoker'
```
