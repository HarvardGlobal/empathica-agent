# Security Baseline

## Identity and access

- Cloud Run service must run as a dedicated runtime service account.
- Follow least privilege for runtime and CI service accounts.
- Human access to production resources must use IAM roles, not static credentials.

## Secrets handling

- Store secrets in Google Secret Manager.
- Do not commit secrets or `.env` files with sensitive values.
- Inject secrets at runtime via environment variables or mounted secret references.

## Network and service access

- Keep Cloud Run service private by default (`--no-allow-unauthenticated`).
- Grant invoker access only to approved callers.
- Restrict outbound calls to approved clinical and platform dependencies.

## Data handling

- Treat patient-linked context as sensitive.
- Avoid logging full PHI payloads in application logs.
- Store documents in scoped GCS prefixes with explicit IAM boundaries.

## Supply chain and build integrity

- Build images through Cloud Build, not local ad-hoc builds for production.
- Pin dependency versions where practical.
- Review dependency updates before merge.

## Incident response baseline

- Capture deployment SHA for every release.
- Maintain rollback instructions and verification checks.
- Document security-impacting incidents and postmortems.
