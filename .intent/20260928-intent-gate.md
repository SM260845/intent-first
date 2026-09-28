---
id: 20260928-intent-gate
status: shipped
touches: [README.md, .github/, scripts/]
---
# Enforce intent-first in CI

## Want
One workflow that makes the README rules real: a PR merges only if it is
about exactly one intent, that intent is well-formed, and shipped intents
stay untouched.

## Not
No external service, no dependencies beyond Python 3 and git.
No blocking on `touches:` scope; warn only.
No editing of shipped intent bodies, including this one, after merge.

## Done when
- The gate, schema, immutability, supersedes and touches rules pass their fixtures
  check: `python3 scripts/test_intent_check.py`
- A junk intent file containing only "hi" fails CI (kill criterion S4)
  check: `python3 scripts/test_intent_check.py | grep -q "^ok .*junk intent 'hi' (kill criterion S4)"`
- `.intent/` changes require review from a CODEOWNER
- README rules match what the workflow enforces
