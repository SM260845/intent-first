---
id: 20261003-inbox-ship-on-branch
status: shipped
touches: [.github/workflows/, inbox/, action.yml, scripts/, README.md, CHANGELOG.md]
---
# Intent Inbox: land the shipped move inside the merge

## Want
For a same-repo claim, the ship job commits the move from `.intent/open/` to
`.intent/shipped/` onto the winning PR's branch, re-runs CI on that commit,
and squash-merges that exact SHA. Nothing is pushed to main, and
`GITHUB_TOKEN` is enough. Only that rename is exempt from the `.intent/`
rule. Fork claims fall back to the optional `INTENT_INBOX_TOKEN`, or leave
the intent in `.intent/open/` with a comment. The leftover demo intent moves
to `.intent/shipped/`.

## Not
No push to main from the ship job for same-repo claims. No other change to
the claim rules or the fork rule. No release is published.

## Done when
- Gate self-tests pass, including moves
  check: `python3 scripts/test_intent_check.py`
- Inbox self-tests pass, including the move exemption
  check: `python3 scripts/test_intent_inbox.py`
- The leftover demo intent is shipped
  check: `test -f .intent/shipped/20261003-inbox-demo.md && test ! -e .intent/open/20261003-inbox-demo.md`
- A fresh claim merges with its intent in `.intent/shipped/`, and main CI is green
