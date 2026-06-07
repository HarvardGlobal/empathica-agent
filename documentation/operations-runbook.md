# Operations Runbook

## Service health checks

- Endpoint: `GET /healthz`
- Expected success: HTTP `200` and body `{"ok": true}`

## Smoke test for chat

- Endpoint: `POST /chat`
- Use a non-sensitive, generic medication question.
- Verify output JSON includes `answer`, `literacy_level`, and `empathy_level`.

## Incident triage

1. Check Cloud Run revision health and recent deploy timestamp.
2. Check Cloud Logging for request errors and timeouts.
3. Validate Vertex model settings and quota availability.
4. Validate optional dependencies (FHIR, GCS, DailyMed API reachability).

## Rollback

```bash
gcloud run revisions list --service empathica-agents --region us-east4
```

```bash
gcloud run services update-traffic empathica-agents \
  --region us-east4 \
  --to-revisions <stable_revision>=100
```
