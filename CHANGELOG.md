# Changelog

## v1.1.2

- `supersedes:` can point at an intent in `.intent/shipped/` (#37 by @kkinsen0314-alt, fixes #31).
- New inputs to skip the gate: `exempt-authors` (default `dependabot[bot],renovate[bot]`), `exempt-paths` (globs) and `skip-label` (default `no-intent`). A skipped PR passes with a notice that says why. A PR that changes `.intent/` is never skipped.
- `git why` finds intents in `.intent/open/` and `.intent/shipped/`, and reads `Claims: <id>` like `Intent: <id>`, so code shipped through the Inbox can be traced.
- `git why --init <slug>` writes today's intent template.
- `touches:` can be a YAML block list, and section headings match regardless of case. The `intent` output stays empty for an id that doesn't exist.
- Plainer notice when a PR has no agent session proof. The "How to fix" link points at a real section.
- README rewritten around the core loop, with a new GIF from a real run, `git blame` vs `git why`, when not to use it, and a comparison table. The Intent Inbox moved to `docs/inbox.md`. New `docs/AGENTS-snippet.md` for coding agents.

## v1.1.1

- intent-intake counts only approvals from owners, members and collaborators, never the PR author's own, and gates any change to `.intent/open/`.
- The inbox reads every page of PR files, issues and PRs. A PR with more than 3000 files is never merged or approved.
- New `claims` mode and a sweep every 30 minutes. `ship` runs one job per intent at a time and retries passing claims that weren't merged. A claim behind the base branch gets one comment asking for an update.
- An intent can be claimed only while its issue is open. Closing the issue as not planned retires it.
- New `protect` input: more paths a claim may never change. This repo protects `action.yml`, `inbox/` and `scripts/`.
- This repo runs its gate and the intake check from the PR's base commit. Checkouts don't keep credentials.
- Tests for the open, intake, claims and ship paths against a fake API. CI runs `tests/` too.

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
