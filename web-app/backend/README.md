# Backend (Express)

## Purpose

This backend is the secure caller for the private Cloud Run medical agent service.

It provides:
- Demo user auth (`/auth/register`, `/auth/login`)
- Authenticated proxy to Cloud Run:
  - `/api/chat`
  - `/api/onboarding/upload`

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

## Auth to private Cloud Run

Uses `google-auth-library` `getIdTokenClient(...)` with audience = `CLOUD_RUN_SERVICE_URL`.

Run this backend where ADC is available (for example Cloud Run with service account attached).

## Database

On startup, backend runs:

- `CREATE TABLE IF NOT EXISTS app_users (...)`

So no manual migration step is required for initial local setup.

Inspect users locally:

```bash
psql postgresql://postgres:postgres@localhost:5432/empathica_web -c "SELECT id,user_id,email,created_at FROM app_users ORDER BY id;"
```
