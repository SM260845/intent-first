---
id: 20260929-proof-carrying-prs
status: draft
touches: [scripts/, .github/workflows/, tests/fixtures/proof/, README.md]
---
# Proof-carrying PRs

## Want
CI verifies agent session proof bundles (.proof/<intent>.json) against the intent and the diff.

## Not
No new dependencies. PRs without a bundle don't fail. No claim that a proof shows the code is correct.

## Done when
- Valid, edited, borrowed, swapped-commit and dropped-event fixtures behave as expected
  check: `python3 scripts/test_proof_check.py`
- A real recorder bundle verifies in a PR
