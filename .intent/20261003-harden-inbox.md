---
id: 20261003-harden-inbox
status: shipped
touches: [.github/, inbox/, scripts/, README.md, CHANGELOG.md, CONTRIBUTING.md]
---
# Harden the Intent Inbox and the gate

## Want
Intake counts only approvals on the latest commit from owners, members and
collaborators, never the PR author, and runs from the base commit. This
repo's gate runs from the base commit too. The inbox reads every page of PR
files, issues and PRs, and refuses PRs with more than 3000 files. Claims
can't change `action.yml`, `inbox/` or `scripts/` here. `ship` runs per
intent, a 30-minute sweep retries passing claims, and a closed issue means
the intent can't be claimed. The README matches the code. The API paths have
tests, and CI runs `tests/`.

## Not
No change to `action.yml` or to intent-check's rules. No change to merged
intents.

## Done when
- Inbox self-tests pass, including author, outsider and closed-issue cases
  check: `python3 scripts/test_intent_inbox.py`
- The open, intake, claims and ship paths pass against a fake API
  check: `python3 scripts/test_intent_inbox_api.py`
- Gate self-tests still pass
  check: `python3 scripts/test_intent_check.py`
- The example tests pass
  check: `python3 -m unittest discover -s tests`
- The gate and the intake check run from the base commit
  check: `grep -q "uses: ./.gate" .github/workflows/proof-carrying-pr.yml && grep -q "base.sha" .github/workflows/intent-intake.yml`
- Required checks are strict, and the sweep runs on schedule
