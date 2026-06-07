# Private Cloud Run Access Setup (Step-by-Step)

This is the simplest production-safe setup:
- Cloud Run service stays **private**.
- Only your backend service account can call it.
- End users call your backend, not Cloud Run directly.

## 1) Cloud setup (one-time)

Use your project:

```bash
gcloud config set project dci-chatbot-476416
```

Get runtime service URL:

```bash
gcloud run services describe empathica-agents \
  --region us-east4 \
  --format='value(status.url)'
```

Make sure `allUsers` is removed:

```bash
gcloud run services remove-iam-policy-binding empathica-agents \
  --region us-east4 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

Grant invoker to your caller service account:

```bash
gcloud run services add-iam-policy-binding empathica-agents \
  --region us-east4 \
  --member="serviceAccount:empathica-invoker@dci-chatbot-476416.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## 2) Backend identity setup

If your backend runs on GCP (recommended):
- Attach `empathica-invoker@...` (or another approved caller SA) to that backend workload.
- Use Application Default Credentials (ADC). No JSON key files needed.

If your backend runs outside GCP:
- Use Workload Identity Federation (recommended), or service-account key as temporary fallback.

## 3) Repo-side client (already included)

Use:

`ops/cloud_run_client.py`

It mints an ID token for Cloud Run audience and calls `/healthz`, `/chat`, `/onboarding/upload`.

### Health check

```bash
python3 ops/cloud_run_client.py \
  --service-url "https://<your-service>.run.app" \
  health
```

### Onboarding upload

```bash
python3 ops/cloud_run_client.py \
  --service-url "https://<your-service>.run.app" \
  onboard \
  --user-id "000-002" \
  --structured-fhir-file "../med_chatbot_webapp/persona-data/mary-rodriguez-johnson/structured_fhir_mary.json" \
  --unstructured-file "../med_chatbot_webapp/persona-data/mary-rodriguez-johnson/unstructured_mary.md" \
  --target-document-types "medication_management,oncology_notes,care_coordination,financial_access,symptom_journal"
```

### Chat request

```bash
python3 ops/cloud_run_client.py \
  --service-url "https://<your-service>.run.app" \
  chat \
  --user-id "000-002" \
  --message "Is ibuprofen safe with my current treatment?" \
  --literacy-level medium \
  --empathy-level medium
```

## 4) What your frontend does

1. User logs into your app.
2. Frontend sends message/files to **your backend**.
3. Backend resolves `user_id` and calls Cloud Run with service-account token.
4. Backend returns Cloud Run response to frontend.

Do not call private Cloud Run directly from browser clients.
