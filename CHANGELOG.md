# Changelog

## v1.1.0 (unreleased)

- Intent Inbox (`ao3575911/intent-first/inbox`). An intent added to `.intent/open/` opens an `intent-open` issue. PRs claim it with `Claims: <id>`. The first claim whose CI passes gets the move to `.intent/shipped/` committed onto its branch, CI re-runs, and that exact SHA is squash-merged, so nothing is pushed to the default branch and `GITHUB_TOKEN` is enough. The other claims and the issue are closed. Fork claims are merged and the intent is moved with the optional `fork-token`, or left in `.intent/open/` with a comment. Assigning a coding agent is optional.
- The action fills in `base-ref` (`origin/<default branch>`) and `head-ref` on `workflow_dispatch` runs, so the inbox can re-run the gate on a claim branch.
- intent-check: `Claims: <id>` runs the `check:` lines of `.intent/open/<id>.md`. A claim fails if the intent has no `check:` lines, if the PR changes `.intent/open/`, or if its checks were skipped (fork PR). Intents may live in `.intent/open/` and `.intent/shipped/`, and moving one from `open/` to `shipped/` is allowed.
- Merged `ao3575911/intent-first-consumer-test` into `examples/consumer/` with its history. The new `consumer-demo` workflow runs the action against it and asserts that the valid intent passes and the junk intent fails.

## v1.0.1

- Moved to `ao3575911/intent-first`. Links to the old owner still redirect, but update your `uses:` lines.
- `run-checks` is skipped on pull requests from forks unless `run-checks-on-forks: "true"` is set, because `check:` lines are code from the PR author.
- The floating `v1` tag now moves automatically when a release is published.
- CI also runs on pushes to `main` (self-tests and ruff), so the badge reflects `main`.
- Added `.gitignore` and removed tracked `__pycache__` files.

## v1.0.0

- One-line installable action, strict touches, proof bundles and `git why`. See the [v1.0.0 release](https://github.com/ao3575911/intent-first/releases/tag/v1.0.0).
