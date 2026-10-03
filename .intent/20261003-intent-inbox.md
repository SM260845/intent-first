---
id: 20261003-intent-inbox
status: shipped
touches: [.github/workflows/, inbox/, scripts/, README.md, CHANGELOG.md]
---
# Intent Inbox: humans write intents, the first passing PR ships

## Want
A human adds an intent to `.intent/open/`. An issue labelled `intent-open`
opens with the intent and how to claim it. Any agent or person opens a PR
with `Claims: <id>`, and intent-check runs that intent's `check:` lines on
it with the existing runner and fork rule. A separate trusted job merges
(squash) the first claiming PR whose CI passes, moves the intent to
`.intent/shipped/`, closes the competing claims with a comment and closes
the issue. Assigning a coding agent to the issue is optional.

## Not
No change to how existing intents, inputs or the fork rule work. No
`pull_request_target`. The trusted job never checks out or runs PR code.
An intent without `check:` lines can't be claimed, and a claiming PR can't
change `.intent/open/`. No release is published.

## Done when
- Gate self-tests pass, including the claim and inbox rules
  check: `python3 scripts/test_intent_check.py`
- Inbox self-tests pass
  check: `python3 scripts/test_intent_inbox.py`
- The demo intent is open
  check: `test -f .intent/open/20261003-inbox-demo.md`
- Live demo: of two claiming PRs, the passing one is merged and the failing one closed
