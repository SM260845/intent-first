---
id: 20261003-supersede-shipped-intents
status: draft
touches: [scripts/intent_check.py, scripts/test_intent_check.py]
---
# Resolve superseded intents in the shipped archive

## Want
Allow a new intent to supersede an existing intent in `.intent/shipped/`.
Use the resolved file path when checking that the superseded intent is
untouched, and add real Git repository regression cases for both outcomes.

## Not
No change to `.intent/open/`, claims, workflows, proof verification, or
top-level intent precedence. No new runtime dependencies.

## Done when
- Superseding an archived intent passes, and editing it is rejected by the untouched-file check
  check: `python3 scripts/test_intent_check.py`
- Proof verification self-tests still pass
  check: `python3 scripts/test_proof_check.py`
- Intent Inbox self-tests still pass
  check: `python3 scripts/test_intent_inbox.py`
- Git why self-tests still pass
  check: `python3 scripts/test_git_why.py`
- Ruff checks pass and changed paths stay inside touches
