# Changelog

## v1.1.0

- Intent Inbox (`ao3575911/intent-first/inbox`). Anyone may propose an intent by PR into `.intent/open/`. The `intent-intake` check (mode `intake`) fails until a human approves the PR's latest commit. A merged intent opens an `intent-open` issue. PRs claim it with `Claims: <id>`. The first claim whose CI passes is squash-merged at the SHA that passed, the other claims are closed, and the issue is closed with the `shipped` label. Intent files never move, and the default `GITHUB_TOKEN` is enough. Assigning a coding agent is optional.
- intent-check: `Claims: <id>` runs the `check:` lines of `.intent/open/<id>.md`. A claim fails if the intent has no `check:` lines, if the PR changes `.intent/`, or if its checks were skipped (fork PR). Files in `.intent/open/` are immutable once merged.
- Added `CONTRIBUTING.md` and issue forms. Rewrote the README, with a replay of the Inbox demo at `docs/inbox-demo.gif`.
- Merged `ao3575911/intent-first-consumer-test` into `examples/consumer/` with its history. The new `consumer-demo` workflow runs the action against it and asserts that the valid intent passes and the junk intent fails.

## v1.0.1

- Moved to `ao3575911/intent-first`. Links to the old owner still redirect, but update your `uses:` lines.
- `run-checks` is skipped on pull requests from forks unless `run-checks-on-forks: "true"` is set, because `check:` lines are code from the PR author.
- The floating `v1` tag now moves automatically when a release is published.
- CI also runs on pushes to `main` (self-tests and ruff), so the badge reflects `main`.
- Added `.gitignore` and removed tracked `__pycache__` files.

## v1.0.0

- One-line installable action, strict touches, proof bundles and `git why`. See the [v1.0.0 release](https://github.com/ao3575911/intent-first/releases/tag/v1.0.0).
