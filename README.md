# Intent-First Repos

> Commit the why. Code is regenerable.

## Problem

Git records what changed, not why.
Agents now write the diff. The instruction behind it is the valuable part, and it dies in a chat log.

## Concept

Every change ships with an **intent**: a short, versioned file stating the goal, the limits, and the proof.

```
.intent/
  0042-rate-limit-login.md
```

```markdown
---
id: 0042
status: shipped
touches: [src/auth/, tests/auth/]
---
# Rate-limit login

## Want
Max 5 failed logins per IP per minute.

## Not
No CAPTCHA. No lockout for real users.

## Done when
- `tests/auth/rate_limit.test` passes
- p95 login latency unchanged
```

Each commit links back with a trailer:

```
Intent: 0042
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

1. One PR, one intent. No intent, no merge.
2. `Done when` must be checkable by CI.
3. Shipped intents are immutable. Supersede, never edit.
4. Humans write intents. Anyone writes code.

## Adopt in three steps

1. Create `.intent/`.
2. Add a PR template that asks for the intent ID.
3. Fail CI when a PR adds no `.intent/*.md`.

No tool. Just a folder and a rule.

## Why now

Code is becoming output. Intent is the source.
A repo that keeps only output is a binary with comments.
