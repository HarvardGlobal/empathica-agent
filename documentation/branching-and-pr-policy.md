# Branching and Pull Request Policy

## Branch roles

- `main`: production branch. Direct pushes are not allowed.
- `develop`: integration branch for validated changes before production.
- `feature/*`: short-lived branches for new features and fixes.
- `hotfix/*`: urgent production fixes with expedited review.

## Required flow

1. Create a branch from `develop` for all new work.
2. Open a pull request into `develop`.
3. Merge to `develop` only after checks pass and required reviews are complete.
4. Open a pull request from `develop` to `main`.
5. Merge to `main` only after explicit approval from the repository owner.

## Main branch approval rule

- Any PR targeting `main` must be approved by Louis Ferger-Andrews (repository owner).
- No self-approval for PRs into `main`.
- Emergency merges still require post-incident review and documented rationale.

## Pull request minimum requirements

- CI checks must pass.
- Deployment impact must be described.
- Security impact must be explicitly marked as `none` or described.
- Rollback strategy must be included for runtime changes.

## Merge strategy

- Use squash merge for feature branches into `develop`.
- Use merge commit from `develop` into `main` to preserve release boundaries.
