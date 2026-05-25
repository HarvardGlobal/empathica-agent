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
