#!/usr/bin/env python3
"""intent-inbox: turn .intent/open/ intents into claimable work.

Usage:
  python3 scripts/intent_inbox.py open     # on push to the default branch: one issue per intent added to .intent/open/
  python3 scripts/intent_inbox.py intake   # on pull_request / pull_request_review: a PR that adds to .intent/open/
                                           # needs an approving review from a human on its latest commit
  python3 scripts/intent_inbox.py ship     # on workflow_run (completed): squash-merge the first passing claim, close
                                           # the competing claims, close the issue with the `shipped` label

Intent files never move. The issue carries the status: closed with `shipped` means the intent shipped.
Env: GITHUB_TOKEN, GITHUB_REPOSITORY, BEFORE and AFTER (open), PR_NUMBER and HEAD_SHA (intake), RUN_ID (ship),
INBOX_ASSIGNEES (optional, comma-separated logins for new issues).
Never checks out or runs pull request code. No dependencies beyond Python 3 and git.
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intent_check import CLAIM_RE, FILENAME_RE, OPEN_DIR, done_when_checks, parse  # noqa: E402

LABEL, SHIPPED = "intent-open", "shipped"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
R = f"/repos/{REPO}"
API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MARKER_RE = re.compile(r"<!-- intent-inbox: (\S+) -->")


# --- pure logic (covered by test_intent_inbox.py)

def claim_of(body):
    """The one valid intent id a PR body claims, else None."""
    ids = set(CLAIM_RE.findall(body or ""))
    c = ids.pop() if len(ids) == 1 else ""
    return c if FILENAME_RE.match(c + ".md") else None


def checks_of(text):
    """The check: commands of an intent's Done when."""
    try:
        return [b["check"] for b in done_when_checks(parse(text)[2]) if b["check"]]
    except ValueError:
        return []


def issue_for(id_, text, path):
    """(title, body) of the issue that opens an inbox intent for claims."""
    body = parse(text)[1].strip()
    m = re.search(r"^#\s+(.+)$", body, re.M)
    title = f"{m.group(1).strip() if m else id_} [{id_}]"
    if checks_of(text):
        how = (f"**To claim it**, open a PR against the default branch with this line in the PR body:\n\n"
               f"    Claims: {id_}\n\n"
               "Any coding agent or person can claim it. CI runs the intent's `check:` lines on the PR. "
               "The first claiming PR whose CI passes is squash-merged, the other claiming PRs are closed, "
               f"and this issue is closed with the `{SHIPPED}` label. The PR may only change paths inside "
               "`touches:`, and never `.intent/` or `.github/`.")
    else:
        how = ("**This intent can't be claimed.** Its Done when has no `check:` lines, so CI can't prove a PR "
               "done. Claiming PRs fail and nothing is auto-merged. Propose a new intent with `check:` lines.")
    link = f"{SERVER}/{REPO}/blob/HEAD/{path}"
    return title, f"<!-- intent-inbox: {id_} -->\nIntent [`{id_}`]({link}) is open.\n\n{body}\n\n---\n\n{how}\n"


def out_of_scope(files, touches):
    """Changed files that block an auto-merge: outside touches:, or under .intent/ or .github/."""
    scope = touches if isinstance(touches, list) else []
    return [f for f in files if f.startswith((".intent/", ".github/"))
            or not any(f == t or f.startswith(t.rstrip("/") + "/") for t in scope)]


def plan(prs, id_, number):
    """(first, competitors) for PR `number` claiming id_. first is False once another claim was merged."""
    others = [p for p in prs if p["number"] != number and claim_of(p.get("body")) == id_]
    return not any(p.get("merged_at") for p in others), [p["number"] for p in others if p["state"] == "open"]


def is_shipped(issue):
    """An intent is shipped once its issue is closed with the `shipped` label."""
    return bool(issue) and issue["state"] == "closed" and SHIPPED in [x["name"] for x in issue.get("labels", [])]


def approvers(reviews, head):
    """Humans whose latest review approves the PR's current head commit. Reviews are in API (chronological) order."""
    latest = {}
    for r in reviews:
        u = r.get("user") or {}
        if u.get("type") == "Bot" or u.get("login", "").endswith("[bot]"):
            continue
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[u.get("login")] = r
    return sorted(k for k, r in latest.items() if r["state"] == "APPROVED" and r.get("commit_id") == head)


# --- GitHub and git

def api(method, path, data=None, soft=False):
    req = urllib.request.Request(API + path, method=method, data=None if data is None else json.dumps(data).encode())
    for k, v in (("Authorization", f"Bearer {TOKEN}"), ("Accept", "application/vnd.github+json"),
                 ("X-GitHub-Api-Version", "2022-11-28")):
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        msg = f"{method} {path}: {e.code} {e.read().decode(errors='replace')[:300]}"
        if soft or e.code == 404:
            print(f"::warning title=intent-inbox::{msg}")
            return None
        raise SystemExit(msg)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {args[0]} failed: {r.stderr.strip()}")
    return r.stdout


def find_issue(id_):
    for i in api("GET", f"{R}/issues?labels={LABEL}&state=all&per_page=100") or []:
        m = MARKER_RE.search(i.get("body") or "")
        if m and m.group(1) == id_:
            return i
    return None


def close(n, msg):
    api("POST", f"{R}/issues/{n}/comments", {"body": msg})
    api("PATCH", f"{R}/pulls/{n}", {"state": "closed"})
    print(f"closed #{n}")


def cmd_open():
    before, after = os.environ.get("BEFORE", ""), os.environ["AFTER"]
    if before.strip("0"):
        out = git("diff", "--name-only", "--no-renames", "--diff-filter=A", before, after, "--", OPEN_DIR)
    else:
        out = git("ls-tree", "-r", "--name-only", after, "--", OPEN_DIR)
    assignees = [a.strip() for a in os.environ.get("INBOX_ASSIGNEES", "").split(",") if a.strip()]
    for path in out.splitlines():
        id_ = os.path.basename(path)[:-3]
        if os.path.dirname(path) + "/" != OPEN_DIR or not FILENAME_RE.match(id_ + ".md"):
            continue
        if find_issue(id_):
            print(f"{id_}: issue exists")
            continue
        text = git("show", f"{after}:{path}")
        try:
            title, body = issue_for(id_, text, path)
        except ValueError as e:
            print(f"::warning title=intent-inbox::{path}: {e}")
            continue
        issue = api("POST", f"{R}/issues", {"title": title, "body": body, "labels": [LABEL]})
        print(f"{id_}: opened {issue['html_url']}")
        if assignees and checks_of(text):
            r = api("POST", f"{R}/issues/{issue['number']}/assignees", {"assignees": assignees}, soft=True)
            if not (r and r.get("assignees")):
                print(f"::warning title=intent-inbox::Could not assign #{issue['number']} to {', '.join(assignees)}. "
                      "Copilot coding agent needs a user token in `token:` (see README).")


def cmd_intake():
    n, head = os.environ["PR_NUMBER"], os.environ["HEAD_SHA"]
    files = api("GET", f"{R}/pulls/{n}/files?per_page=100")
    adds = [f["filename"] for f in files if f["filename"].startswith(OPEN_DIR) and f["status"] in ("added", "renamed", "copied")]
    if not adds:
        return print(f"no intents proposed in {OPEN_DIR}")
    who = approvers(api("GET", f"{R}/pulls/{n}/reviews?per_page=100"), head)
    if who:
        return print(f"intake approved by {', '.join(who)}: {', '.join(adds)}")
    print(f"::error title=intent-intake::This PR proposes {', '.join(adds)}. It needs an approving review from a "
          "human (not a bot) on its latest commit before it can merge.")
    return 1


def cmd_ship():
    run = api("GET", f"{R}/actions/runs/{os.environ['RUN_ID']}")
    if run["conclusion"] != "success" or run["event"] != "pull_request":
        return print("run did not pass on a pull_request event")
    sha = run["head_sha"]
    runs = api("GET", f"{R}/actions/workflows/{run['workflow_id']}/runs?head_sha={sha}&event=pull_request&per_page=100")
    if any(x["id"] > run["id"] for x in runs["workflow_runs"]):
        return print("a newer run exists for this commit; it decides")
    pr = next((p for p in api("GET", f"{R}/pulls?state=open&per_page=100") if p["head"]["sha"] == sha), None)
    id_ = claim_of(pr and pr["body"])
    if not pr or not id_:
        return print(f"no open PR at {sha[:12]} with a Claims: line")
    n, branch = pr["number"], pr["base"]["repo"]["default_branch"]
    if pr["base"]["ref"] != branch:
        return print(f"#{n} does not target {branch}")
    issue = find_issue(id_)
    first, competitors = plan(api("GET", f"{R}/pulls?state=all&sort=updated&direction=desc&per_page=100"), id_, n)
    if is_shipped(issue) or not first:
        return close(n, f"Closing: intent `{id_}` has already shipped.")
    got = api("GET", f"{R}/contents/{OPEN_DIR}{id_}.md?ref={branch}")
    if not got:
        return print(f"{OPEN_DIR}{id_}.md is not on {branch}")
    text = base64.b64decode(got["content"]).decode("utf-8")
    if not checks_of(text):
        return print(f"{id_} has no check: lines, so it can't be claimed")
    blocked = out_of_scope([f["filename"] for f in api("GET", f"{R}/pulls/{n}/files?per_page=100")],
                           parse(text)[0].get("touches"))
    if blocked:
        print(f"::warning title=intent-inbox::Not auto-merging #{n}: {', '.join(blocked)} outside touches: "
              "or under .intent/ or .github/. A human can review and merge it.")
        return
    api("PUT", f"{R}/pulls/{n}/merge", {"merge_method": "squash", "sha": sha, "commit_title": f"{pr['title']} (#{n})",
                                         "commit_message": f"Intent: {id_}\nClaims: {id_}\nHead: {sha}"})
    print(f"merged #{n} at {sha[:12]} for {id_}")
    for c in competitors:
        close(c, f"Closing: #{n} claimed `{id_}` and passed its checks first, so it was merged.")
    if issue and issue["state"] == "open":
        api("POST", f"{R}/issues/{issue['number']}/comments", {"body": f"Shipped in #{n}: {pr['html_url']}"})
        api("POST", f"{R}/issues/{issue['number']}/labels", {"labels": [SHIPPED]})
        api("PATCH", f"{R}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    cmds = {"open": cmd_open, "intake": cmd_intake, "ship": cmd_ship}
    if mode not in cmds:
        raise SystemExit(__doc__)
    sys.exit(cmds[mode]())
