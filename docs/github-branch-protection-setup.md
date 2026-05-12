# GitHub Branch Protection Setup

Configure protections for both `main` and `develop`.

## `main` protection rules

- Require a pull request before merging.
- Require approvals: at least 1.
- Require review from Code Owners.
- Require status checks to pass before merging.
- Restrict who can push directly to matching branches.
- Disable force pushes.

## `develop` protection rules

- Require a pull request before merging.
- Require status checks to pass before merging.
- Disable force pushes.

## Recommended checks

- Test suite (`pytest`)
- Build validation (`docker build`)
- Optional security/dependency scan
