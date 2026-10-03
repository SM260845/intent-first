# Contributing

Thanks for stopping by. This project is small on purpose, so a focused PR can land fast.

## Setup

```bash
git clone https://github.com/ao3575911/intent-first && cd intent-first
python3 scripts/test_intent_check.py   # gate rules
python3 scripts/test_proof_check.py    # proof bundles (needs openssl)
python3 scripts/test_intent_inbox.py   # Intent Inbox
python3 scripts/test_git_why.py        # git why
pipx run ruff check .
```

No dependencies beyond Python 3, git and `openssl`.

## Every PR needs an intent

This repo runs its own gate. Each PR adds exactly one `.intent/YYYYMMDD-slug.md` (Want / Not / Done when), or references an existing draft with `Intent: <id>` in the PR body. CI fails without one. See the [rules](README.md#rules) and the [PR template](.github/PULL_REQUEST_TEMPLATE.md).

- Add `check:` lines under Done when where you can. CI runs them.
- Keep changed paths inside the intent's `touches:`.
- Shipped intents are immutable. To change one, add a new intent with `supersedes:`.
- To propose work for others, add an intent to `.intent/open/`. It merges after a maintainer approves it, then anyone can claim it (see [Intent Inbox](README.md#intent-inbox)).

## Where things live

| Path | What |
|---|---|
| `scripts/intent_check.py` | The gate: schema, one intent per PR, immutability, touches, `check:` lines, claims |
| `scripts/proof_check.py` | Verifies sealed agent session proofs |
| `scripts/intent_inbox.py`, `inbox/` | Intent Inbox: intake check, issues, ship job |
| `action.yml` | The composite action (intent-check, then proof-check) |
| `bin/git-why` | `git why <file>:<line>` |
| `tests/fixtures/`, `examples/consumer/` | Fixtures. Never commit real agent sessions |

## Good first issues

- [#31](https://github.com/ao3575911/intent-first/issues/31) `supersedes:` can't point at an intent in `.intent/shipped/`
- [#32](https://github.com/ao3575911/intent-first/issues/32) Warn on unknown frontmatter keys (catches `supercedes:` typos)

More under [good first issue](https://github.com/ao3575911/intent-first/labels/good%20first%20issue).

## Pull requests

- Keep PRs small and focused. Open an issue first for anything big.
- A change to the gate needs a self-test case in `scripts/test_*.py` that shows the new pass or fail.
- Self-tests and ruff must pass. Changes to `.intent/`, `.github/` and `scripts/` need review from @ao3575911 (CODEOWNERS).
- Don't switch workflows to `pull_request_target`. `check:` lines are code from the PR author.

## Security

Report security issues privately through [GitHub private vulnerability reporting](https://github.com/ao3575911/intent-first/security/advisories/new), not in public issues.
