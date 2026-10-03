---
id: 20260929-require-proof
status: shipped
touches: [scripts/, action.yml, README.md]
---
# Optional require-proof mode

## Want
Repos can make a sealed session proof mandatory, so an agent can't skip it.

## Not
Default stays off; PRs without a proof still pass unless the repo opts in.

## Done when
- A PR with no bundle fails under --require-proof and passes without it
  check: `python3 scripts/test_proof_check.py`
