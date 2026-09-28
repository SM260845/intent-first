---
id: 20260929-one-action
status: draft
touches: [action.yml, .github/workflows/, README.md]
---
# One action for why, how and what

## Want
A single reusable GitHub Action that checks a PR's intent (why), its sealed agent session proof (how) and the diff (what) in one step.

## Not
No new checks or dependencies. It only composes intent_check.py and proof_check.py.

## Done when
- Both self-tests pass
  check: `python3 scripts/test_intent_check.py && python3 scripts/test_proof_check.py`
- This PR passes through `uses: ./`
