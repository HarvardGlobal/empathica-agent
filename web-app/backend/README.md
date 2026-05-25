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

## Environment

- `PORT`
- `APP_JWT_SECRET`
- `CLOUD_RUN_SERVICE_URL`
- `CORS_ORIGIN`

## Auth to private Cloud Run

Uses `google-auth-library` `getIdTokenClient(...)` with audience = `CLOUD_RUN_SERVICE_URL`.

Run this backend where ADC is available (for example Cloud Run with service account attached).
