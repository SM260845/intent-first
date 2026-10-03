# Changelog

## v1.0.1

- Moved to `ao3575911/intent-first`. Links to the old owner still redirect, but update your `uses:` lines.
- `run-checks` is skipped on pull requests from forks unless `run-checks-on-forks: "true"` is set, because `check:` lines are code from the PR author.
- The floating `v1` tag now moves automatically when a release is published.
- CI also runs on pushes to `main` (self-tests and ruff), so the badge reflects `main`.
- Added `.gitignore` and removed tracked `__pycache__` files.

## v1.0.0

- One-line installable action, strict touches, proof bundles and `git why`. See the [v1.0.0 release](https://github.com/ao3575911/intent-first/releases/tag/v1.0.0).
