# Backend (Express)

## Purpose

This backend is the secure caller for the private Cloud Run medical agent service.

It provides:
- Demo user auth (`/auth/register`, `/auth/login`)
- Authenticated proxy to Cloud Run:
  - `/api/chat`
  - `/api/onboarding/upload`
- Server-side identity mapping:
  - App user (`app_users.user_id`) -> Cloud patient identity (`app_users.cloud_user_id`)
  - Optional `tenant` and `status` are also enforced server-side

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

Note:
- This backend is pinned to Node 20 runtime through npm scripts (`npx node@20`) to avoid local incompatibilities seen with Node 25.

## Environment

- `PORT`
- `APP_JWT_SECRET`
- `CLOUD_RUN_SERVICE_URL`
- `CORS_ORIGIN`
- `DATABASE_URL` (PostgreSQL connection string)

Recommended for production:
- `PGSSLMODE=require`
- `PG_SSL_REJECT_UNAUTHORIZED=true`

## Auth to private Cloud Run

Uses `google-auth-library` `getIdTokenClient(...)` with audience = `CLOUD_RUN_SERVICE_URL`.

Run this backend where ADC is available.

Current recommended mode:
- Web Backend runs outside GCP (local/self-hosted)
- Set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key that has `roles/run.invoker` on `empathica-agents`

Optional future mode:
- If Web Backend runs on Cloud Run, attach runtime service account and grant it `roles/run.invoker` on `empathica-agents`.

## Database

On startup, backend performs additive schema setup on `app_users`:
- `name`
- `cloud_user_id`
- `tenant` (default `default`)
- `status` (default `active`)
- `last_structured_update_at`
- `last_unstructured_update_at`

It also creates chat tables (`chat_threads`, `chat_messages`) if missing.

Inspect users locally:

```bash
psql "$DATABASE_URL" -c "SELECT id,user_id,email,cloud_user_id,tenant,status,created_at FROM app_users ORDER BY id;"
```

Set/verify cloud identity mapping for a user:

```bash
psql "$DATABASE_URL" \
  -v app_email='mary@dci.com' \
  -v cloud_user_id='000-002' \
  -v tenant='default' \
  -v status='active' \
  -f web-app/scripts/set_user_cloud_mapping.sql
```
