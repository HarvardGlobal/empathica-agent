# Contributing

## Workflow summary

1. Sync local `develop` with remote.
2. Create a `feature/*` or `fix/*` branch from `develop`.
3. Implement changes and open a PR into `develop`.
4. After merge to `develop`, include changes in a release PR from `develop` to `main`.
5. Merge to `main` only after repository owner approval.

## Branch naming

- `feature/<short-description>`
- `fix/<short-description>`
- `hotfix/<short-description>`

## PR expectations

- Clear summary and scope.
- Test evidence (`pytest -q` output in PR notes).
- Deployment and security impact called out.
- Architecture docs updated if component boundaries change.

## Do not

- Do not push directly to `main`.
- Do not merge feature branches into `main`.
- Do not bypass review requirements for routine changes.
