# Release Checklist

## Pre-PR checks

- `pytest -q` passes locally or in CI.
- Deployment-impacting env vars are documented.
- Security impact is reviewed.
- Rollback notes are included in PR description.

## Develop merge checks

- PR targets `develop`.
- CI pipeline is green.
- At least one reviewer approval is present.
- Any architecture-impacting changes are reflected in docs.

## Main merge checks

- PR source branch is `develop`.
- Repository owner approval is present.
- Release notes summarize user-facing and operational changes.
- Cloud Build and Cloud Run settings are verified for the release.

## Post-merge checks

- Confirm deployed image/tag matches merged commit SHA.
- Validate `/healthz` and a representative `/chat` request.
- Record release timestamp, SHA, and approver.
