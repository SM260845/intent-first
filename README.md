# Intent-First Repos

> Commit the why. Code is regenerable.

[![intent-check](https://github.com/SM260845/intent-first/actions/workflows/proof-carrying-pr.yml/badge.svg)](https://github.com/SM260845/intent-first/actions/workflows/proof-carrying-pr.yml)

Original essay: [gist](https://gist.github.com/SM260845/5db513ca90679e0d5845b601ae9e6a5c). This README holds the current rules, revised after dogfooding.

## Install in 30 seconds

**1. Add the gate** as `.github/workflows/intent-check.yml`, then make `intent-check` a required status check:

```yaml
name: intent-check
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
jobs:
  intent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: {fetch-depth: 0}
      - uses: SM260845/intent-first@v1
        # with: {strict-touches: "true"}   # fail, not warn, on paths outside touches:
```

**2. Write your first intent** as `.intent/20261001-first-intent.md` in the same PR:

```markdown
---
id: 20261001-first-intent
status: draft
touches: [.github/, .intent/]
---
# Adopt intent-first

## Want
Every PR states its intent.

## Not
No other changes.

## Done when
- The intent-check job passes on this PR
```

**3. Install `git why`** to go from any line to its intent:

```sh
curl -fsSL https://raw.githubusercontent.com/SM260845/intent-first/v1/bin/git-why -o ~/.local/bin/git-why && chmod +x ~/.local/bin/git-why
git why src/ratelimit.py:21   # commit, intent id, status, PR, supersede chain, Want / Not / Done when
```

Inputs: `base-ref`, `head-ref` (default: the PR's), `strict-touches` (default `false`), `run-checks` (default `true`), `proof-check` (default `true`), `require-proof` (default `false`). Live example: [SM260845/intent-first-consumer-test](https://github.com/SM260845/intent-first-consumer-test) (PR #1 passes, PR #2 with a junk `hi` intent fails).

## Problem

Git records what changed, not why.
Agents now write the diff. The instruction behind it is the valuable part, and it gets lost in a chat log.

## Concept

Every change ships with an **intent**: a short, versioned file that states the goal, the limits, and the proof.

```
.intent/
  20260928-rate-limit-login.md
```

```markdown
---
id: 20260928-rate-limit-login
status: draft            # draft -> shipped. Nothing else changes once shipped.
touches: [src/, tests/]
---
# Rate-limit failed logins

## Want
Max 5 failed logins per IP per minute.

## Not
No CAPTCHA. No lockout for users who log in successfully.

## Done when
- Limiter unit tests pass
  check: `python3 -m unittest discover -s tests`
- p95 login latency unchanged
```

Each commit or PR links back with a trailer:

```
Intent: 20260928-rate-limit-login
```

## What changes

| Today | Intent-first |
|---|---|
| Review the diff | Review the intent, then verify the diff |
| `git blame` says who | `git blame` leads to why |
| Refactors are risky | Refactors are re-runs against the same intents |
| Forks copy code | Forks copy decisions |
| Docs drift | Intents are a log. Logs don't need updating |

## Rules

These are enforced by [`scripts/intent_check.py`](scripts/intent_check.py) via [`action.yml`](action.yml).

1. **One PR, one intent.** A PR must be about exactly one intent. It can either
   - add one new `.intent/*.md`, **or**
   - reference one existing **draft** intent with `Intent: <id>` in the PR body or a commit trailer.

   Adding a file isn't enough on its own. Zero intents fail, and so do two.
2. **Schema.** Frontmatter needs `id`, `status` (`draft` | `shipped`), and `touches` (a list). The body needs a `# Title` and non-empty `## Want`, `## Not`, and `## Done when` sections, and Done when needs at least one `- ` bullet. `id` must equal the filename.
3. **IDs are date-slugs.** `YYYYMMDD-short-slug.md`, e.g. `20260928-rate-limit-login.md`. You don't hand-pick numbers, so parallel branches don't collide.
4. **Shipped is immutable.** A draft can be edited, and its `status` can flip `draft → shipped`. Once `status: shipped` is on `main`, CI rejects any edit, rename, or deletion of that file.
5. **Supersede, never edit.** To change a shipped decision, add a new intent with `supersedes: <old-id>`. The old id must exist, and the old file must not change in that PR.
6. **Humans own intents.** [`CODEOWNERS`](.github/CODEOWNERS) requires review from @SM260845 on `.intent/`. Anyone (or any agent) can write code.
7. **Done when is checkable where possible.** An indented ``check: `cmd` `` line under a bullet is run by CI, and a non-zero exit fails the PR. Bullets without `check:` go to human review and are listed in the job summary.
8. **Stay in scope.** CI puts a warning annotation on every changed path outside the intent's `touches:`. It warns by default; `strict-touches: "true"` (`--touches=fail`) makes it fail.

A junk intent (`.intent/hi.md` containing only `hi`) fails CI. That was the kill criterion for this design, and a self-test fixture checks it on every PR.

## Adopt in four steps

1. Create `.intent/` and write your first intent (`YYYYMMDD-slug.md`).
2. Copy [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) (it asks for Intent ID, link, and Done when).
3. Add the workflow from [Install in 30 seconds](#install-in-30-seconds), then mark `intent-check` as a required status check.
4. Add `/.intent/ @your-team` to `.github/CODEOWNERS` and turn on "Require review from Code Owners".

No framework. It's a folder, one dependency-free Python script, and a rule.

Run it locally:

```sh
python3 scripts/intent_check.py --base origin/main --head HEAD --pr-body-file pr.md
python3 scripts/test_intent_check.py   # fixtures for every rule
```

> **Security note:** `check:` commands come from the PR itself. The workflow runs on `pull_request` with a read-only `contents` token and no secrets, so fork PRs can't reach anything privileged. Don't switch it to `pull_request_target`.

## Proof-carrying PRs

An intent says why. A proof bundle shows how the agent got there, and CI checks both against the diff.

```sh
agent-session-recorder bundle <sessionId> --intent 20260928-rate-limit-login --timestamp
git add .proof/ && git commit -m "proof for 20260928-rate-limit-login"
```

`bundle` (from [agent-session-recorder](https://github.com/SM260845/agent-session-recorder)) writes a `proof.link` event naming the intent and the current commit into the sealed session, Merkle-batches it with an RFC 3161 timestamp, and saves `.proof/<intent-id>.json`.

[`scripts/proof_check.py`](scripts/proof_check.py) re-implements the verifier independently with no third-party Python packages, requires the `openssl` executable for RFC 3161 checks, and fails the PR if:

- any session event was edited, dropped, inserted or reordered
- any event isn't covered by a Merkle batch, or a timestamp doesn't cover its batch
- the sealed link names a different intent or commit (a proof borrowed from another intent)
- the intent file doesn't exist, or the linked commit isn't in the PR
- code changed after the linked commit (only `.proof/` and `.intent/` may follow it)

PRs without a bundle pass with a notice and are treated as human-authored. The bundle proves the session record wasn't altered. It doesn't prove the agent reported truthfully, or that the code is correct.

## Demo walkthrough

The demo feature is a login rate limiter ([#1](https://github.com/SM260845/intent-first/issues/1)). Five proof PRs exercise the gate:

| # | Proof | Expected | What it shows |
|---|---|---|---|
| [#5](https://github.com/SM260845/intent-first/pull/5) | New intent + code | ✅ pass, merged | Adds `20260928-rate-limit-login` as `draft` with the limiter and tests |
| [#6](https://github.com/SM260845/intent-first/pull/6) | Follow-up on the same draft | ✅ pass, merged | No new file. References the draft via `Intent:`, fixes a bug, and flips it to `shipped` |
| [#7](https://github.com/SM260845/intent-first/pull/7) | Junk intent `hi` | ❌ fail (schema) | The kill criterion |
| [#8](https://github.com/SM260845/intent-first/pull/8) | Edit a shipped intent's body | ❌ fail (immutability) | Shipped is append-only |
| [#9](https://github.com/SM260845/intent-first/pull/9) | Supersede | ✅ pass, merged | New intent with `supersedes:`; the old file is untouched |

Every PR body carries its `Intent:` id and commit SHA(s). Every merge commit carries an `Intent:` trailer and the merged head SHA. [#4](https://github.com/SM260845/intent-first/pull/4) put this gate in place and went through the gate itself.

## Why now

Code is becoming output. Intent is the source.
A repo that keeps only output is a binary with comments.

## One action for why, how and what

Other repos can use both gates in one step. Add `.intent/` files as usual, and have the agent run `agent-session-recorder bundle <session> --intent <id> --timestamp` before opening the PR:

```yaml
on: {pull_request: {types: [opened, synchronize, reopened, edited]}}
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: {fetch-depth: 0, ref: "${{ github.event.pull_request.head.sha }}"}
      - uses: SM260845/intent-first@v1   # intent-check, then proof-check
        with: {run-checks: "true", require-proof: "false"}  # "true" fails PRs with no sealed session
```

The intent says why, the sealed session in `.proof/<intent>.json` shows how the agent got there, and the diff is checked against both. PRs without a proof still need an intent and pass the proof step with a notice.
