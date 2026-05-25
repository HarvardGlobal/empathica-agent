# Mary Persona Upload Package

This folder contains onboarding-ready files for Mary.

## Files
- `structured_fhir_mary.json`: FHIR Bundle (Patient + allergies + conditions + medications + observations)
- `unstructured_mary.md`: clinical/social narrative context

## Suggested onboarding call
```bash
SERVICE_URL=$(gcloud run services describe empathica-agents --region us-east4 --format='value(status.url)')

curl -sS -X POST "$SERVICE_URL/onboarding/upload" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -F "user_id=000-002" \
  -F "tenant=default" \
  -F "status=active" \
  -F "structured_fhir_file=@persona-data/mary-rodriguez-johnson/structured_fhir_mary.json;type=application/json" \
  -F "unstructured_file=@persona-data/mary-rodriguez-johnson/unstructured_mary.md;type=text/markdown"
```
