#!/usr/bin/env python3
"""Self-test for intent_inbox.py: claims, checks, issue text, who wins, claimable status, protected paths and intake approval. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intent_inbox import approvers, checks_of, claim_of, claimable, issue_for, out_of_scope, plan, protected  # noqa: E402

WITH = """---
id: 20261003-demo
status: draft
touches: [examples/inbox-demo/]
---
# Greet

## Want
A greeting.

## Not
Nothing else.

## Done when
- It prints the line
  check: `sh examples/inbox-demo/greet.sh | grep -qx 'hello from the intent inbox'`
"""
WITHOUT = WITH.replace("  check: `sh examples/inbox-demo/greet.sh | grep -qx 'hello from the intent inbox'`\n", "")
PRS = [  # newest first, as the API returns them
    {"number": 3, "state": "open", "merged_at": None, "body": "Claims: 20261003-demo"},
    {"number": 2, "state": "open", "merged_at": None, "body": "Fix\n\nClaims: `20261003-demo`\n"},
    {"number": 1, "state": "open", "merged_at": None, "body": "Claims: 20261003-other"},
]



def rv(login, state, commit, kind="User", assoc="COLLABORATOR"):
    return {"user": {"login": login, "type": kind}, "state": state, "commit_id": commit, "author_association": assoc}


cases = [
    ("claim_of reads one claim", claim_of("x\nClaims: 20261003-demo\n") == "20261003-demo"),
    ("claim_of ignores two claims", claim_of("Claims: 20261003-a\nClaims: 20261003-b") is None),
    ("claim_of ignores bad ids", claim_of("Claims: ../etc") is None and claim_of(None) is None),
    ("checks_of finds check: lines", len(checks_of(WITH)) == 1 and checks_of(WITHOUT) == []),
    ("issue tells how to claim", "Claims: 20261003-demo" in issue_for("20261003-demo", WITH, "p")[1]),
    ("issue title comes from the intent", issue_for("20261003-demo", WITH, "p")[0] == "Greet [20261003-demo]"),
    ("issue says an intent without checks can't be claimed",
     "can't be claimed" in issue_for("20261003-demo", WITHOUT, "p")[1]),
    ("first passing claim wins, other claims are competitors", plan(PRS, "20261003-demo", 2) == (True, [3])),
    ("a claim after a merged one is not first",
     plan([dict(PRS[0], state="closed", merged_at="2026-10-03T00:00:00Z")] + PRS[1:], "20261003-demo", 2)[0] is False),
    ("in-scope files may auto-merge", out_of_scope(["examples/inbox-demo/greet.sh"], ["examples/inbox-demo/"]) == []),
    ("files outside touches block auto-merge", out_of_scope(["scripts/x.py"], ["examples/inbox-demo/"]) == ["scripts/x.py"]),
    ("intent files block auto-merge", out_of_scope([".intent/open/X.md"], [".intent/"]) != []),
    ("an open issue is claimable", claimable({"state": "open", "labels": []})),
    ("a closed issue is not claimable, shipped or not planned",
     not claimable({"state": "closed", "labels": [{"name": "shipped"}]})
     and not claimable({"state": "closed", "labels": [{"name": "intent-open"}]}) and not claimable(None)),
    ("protect: adds paths to .intent/ and .github/", protected("action.yml, scripts/") == (".intent/", ".github/", "action.yml", "scripts/")),
    ("protect: a protected file blocks auto-merge even inside touches",
     out_of_scope(["scripts/x.py", "action.yml"], ["scripts/", "action.yml"], protected("action.yml,scripts/"))
     == ["scripts/x.py", "action.yml"]),
    ("protect: a protected prefix doesn't block a sibling", out_of_scope(["scripts2/x"], ["scripts2/"], protected("scripts/")) == []),
    ("intake: a human approval on the head commit counts", approvers([rv("ann", "APPROVED", "h2")], "h2") == ["ann"]),
    ("intake: a bot approval doesn't count",
     approvers([rv("copilot-swe-agent[bot]", "APPROVED", "h2", "Bot"), rv("ci", "APPROVED", "h2", "Bot")], "h2") == []),
    ("intake: an approval of an older commit doesn't count", approvers([rv("ann", "APPROVED", "h1")], "h2") == []),
    ("intake: changes requested after an approval cancels it",
     approvers([rv("ann", "APPROVED", "h2"), rv("ann", "CHANGES_REQUESTED", "h2")], "h2") == []),
    ("intake: the PR author's own approval doesn't count", approvers([rv("dev", "APPROVED", "h2", assoc="OWNER")], "h2", "dev") == []),
    ("intake: an approval from outside the repo doesn't count",
     approvers([rv("eve", "APPROVED", "h2", assoc="NONE"), rv("bob", "APPROVED", "h2", assoc="CONTRIBUTOR")], "h2") == []),
    ("intake: owners and members count", approvers([rv("o", "APPROVED", "h2", assoc="OWNER"), rv("m", "APPROVED", "h2", assoc="MEMBER")], "h2", "dev") == ["m", "o"]),
    ("intake: comments don't cancel an approval",
     approvers([rv("ann", "APPROVED", "h2"), rv("ann", "COMMENTED", "h2")], "h2") == ["ann"]),
    ("workflow changes block auto-merge", out_of_scope([".github/workflows/x.yml"], [".github/"]) != []),
]
fails = 0
for name, ok in cases:
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {name}")
print(f"\n{len(cases) - fails}/{len(cases)} cases behave as specified")
sys.exit(1 if fails else 0)
