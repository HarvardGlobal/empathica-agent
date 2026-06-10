# Contributing

This repository follows a simple branch-based workflow.

## Branch model

- `main` is the deployment branch.
- `develop` is the active integration branch.
- feature work starts from `develop`.
- stable milestone releases move from `develop` to `main`.

## Branch naming

Use clear branch names:

- `feature/<ticket>-<short-description>`
- `fix/<ticket>-<short-description>`
- `chore/<short-description>`
- `hotfix/<ticket>-<short-description>`

## Pull requests

- Open pull requests into `develop` for normal feature work.
- Open pull requests into `main` only for approved release promotion or urgent hotfixes.
- Keep pull requests focused on one change set.
- Include a short summary of the change, testing performed, and any deployment impact.

## Release flow

1. Branch from `develop`.
2. Implement the change on a feature branch.
3. Merge through a pull request into `develop`.
4. Test and stabilize `develop`.
5. Merge `develop` into `main` for deployment.

## Expectations

- Keep `main` production-ready.
- Avoid direct commits to `main`.
- Update documentation when workflow or deployment behavior changes.
