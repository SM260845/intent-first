---
id: 20261003-inbox-issue-status
status: shipped
touches: [.github/, inbox/, action.yml, scripts/, README.md, CHANGELOG.md, CONTRIBUTING.md]
---
# Intent Inbox: the issue carries the status, intake needs a human approval

## Want
Intent files never move. When the first passing claim is merged, its issue
is closed with the `shipped` label and a link to the winning PR, and an
intent counts as shipped once its issue is closed that way. Anyone, human
or agent, may propose an intent by PR into `.intent/open/`, and the
`intent-intake` check fails that PR until a human approves its latest
commit. It re-runs on `pull_request_review`. Claim PRs can't change
`.intent/`. The branch-push, move and `INTENT_INBOX_TOKEN` logic is gone.
Add CONTRIBUTING.md and issue forms.

## Not
No change to `.intent/shipped/` or to merged files in `.intent/open/`. No
change to the fork rule. No release is published.

## Done when
- Gate self-tests pass, including immutable open intents and claim rules
  check: `python3 scripts/test_intent_check.py`
- Inbox self-tests pass, including shipped status and intake approval
  check: `python3 scripts/test_intent_inbox.py`
- No move or token logic remains
  check: `! grep -rnE "INTENT_INBOX_TOKEN|fork-token|commit_move" inbox scripts .github README.md action.yml`
- Contributor docs exist
  check: `test -f CONTRIBUTING.md && test -f .github/ISSUE_TEMPLATE/bug.yml && test -f .github/ISSUE_TEMPLATE/feature.yml && test -f .github/ISSUE_TEMPLATE/config.yml`
- A PR that proposes an intent fails intent-intake until a human approves it
