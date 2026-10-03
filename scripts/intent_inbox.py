#!/usr/bin/env python3
"""intent-inbox: turn .intent/open/ intents into claimable work.

Usage:
  python3 scripts/intent_inbox.py open     # on push to the default branch: one issue per intent added to .intent/open/
  python3 scripts/intent_inbox.py intake   # on pull_request / pull_request_review: a PR that changes .intent/open/
                                           # needs an approving review on its latest commit from an owner, member or
                                           # collaborator who isn't the PR author
  python3 scripts/intent_inbox.py claims   # on workflow_run (RUN_ID), schedule or workflow_dispatch (sweep): the
                                           # passing claims as JSON, one per intent, in the `claims` step output
  python3 scripts/intent_inbox.py ship     # merge the claim whose run passed (RUN_ID), close the competing claims,
                                           # close the issue with the `shipped` label

Intent files never move. The issue carries the status: an intent can be claimed only while its issue is open.
Env: GITHUB_TOKEN, GITHUB_REPOSITORY, BEFORE and AFTER (open), PR_NUMBER and HEAD_SHA (intake), RUN_ID (claims on
workflow_run, and ship), INBOX_WORKFLOW (claims sweep: the CI workflow file), INBOX_PROTECT (extra comma-separated
paths a claim may never change), INBOX_ASSIGNEES (optional, comma-separated logins for new issues).
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
MAX_FILES = 3000  # the API lists at most 3000 files of a PR
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
ALWAYS_PROTECTED = (".intent/", ".github/")
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
               "`touches:`, and never `.intent/` or `.github/`. Claims count only while this issue is open.")
    else:
        how = ("**This intent can't be claimed.** Its Done when has no `check:` lines, so CI can't prove a PR "
               "done. Claiming PRs fail and nothing is auto-merged. Propose a new intent with `check:` lines.")
    link = f"{SERVER}/{REPO}/blob/HEAD/{path}"
    return title, f"<!-- intent-inbox: {id_} -->\nIntent [`{id_}`]({link}) is open.\n\n{body}\n\n---\n\n{how}\n"


def protected(extra=""):
    """Paths a claim may never change: .intent/, .github/ and the comma-separated extras."""
    return ALWAYS_PROTECTED + tuple(p.strip() for p in (extra or "").split(",") if p.strip())


def _under(f, p):
    p = p.rstrip("/")
    return f == p or f.startswith(p + "/")


def out_of_scope(files, touches, protect=ALWAYS_PROTECTED):
    """Changed files that block an auto-merge: outside touches:, or under a protected path."""
    scope = touches if isinstance(touches, list) else []
    return [f for f in files if any(_under(f, p) for p in protect) or not any(_under(f, t) for t in scope)]


def plan(prs, id_, number):
    """(first, competitors) for PR `number` claiming id_. first is False once another claim was merged."""
    others = [p for p in prs if p["number"] != number and claim_of(p.get("body")) == id_]
    return not any(p.get("merged_at") for p in others), [p["number"] for p in others if p["state"] == "open"]


def claimable(issue):
    """An intent can be claimed only while its issue is open. Closed means shipped or not planned."""
    return bool(issue) and issue.get("state") == "open"


def approvers(reviews, head, author=""):
    """Owners, members and collaborators, other than the PR author, whose latest review approves the PR's
    current head commit. Reviews are in API (chronological) order."""
    latest = {}
    for r in reviews:
        u = r.get("user") or {}
        login = u.get("login", "")
        if u.get("type") == "Bot" or login.endswith("[bot]") or login.lower() == (author or "").lower():
            continue
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = r
    return sorted(k for k, r in latest.items() if r["state"] == "APPROVED" and r.get("commit_id") == head
                  and r.get("author_association") in TRUSTED)


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


def pages(path, limit=100):
    """Every item of a paginated list endpoint, up to `limit` pages of 100."""
    sep, out = "&" if "?" in path else "?", []
    for page in range(1, limit + 1):
        got = api("GET", f"{path}{sep}per_page=100&page={page}") or []
        out += got
        if len(got) < 100:
            break
    return out


def pr_files(pr):
    """Every changed file of a PR (dicts with filename and status). Fails above MAX_FILES, which the API can't list."""
    if (pr.get("changed_files") or 0) > MAX_FILES:
        raise SystemExit(f"#{pr['number']} changes {pr['changed_files']} files. The API lists at most {MAX_FILES}, "
                         "so the inbox can't check it.")
    return pages(f"{R}/pulls/{pr['number']}/files", MAX_FILES // 100)


def inbox_issues():
    """{intent id: its issue} over every issue labelled intent-open."""
    out = {}
    for i in pages(f"{R}/issues?labels={LABEL}&state=all"):
        m = MARKER_RE.search(i.get("body") or "")
        if m:
            out.setdefault(m.group(1), i)
    return out


def pr_at(sha):
    """The open PR whose head is sha, else None."""
    return next((p for p in pages(f"{R}/pulls?state=open") if p["head"]["sha"] == sha), None)


def latest_run(workflow, sha):
    """The newest pull_request run of a workflow (id or file name) at sha, else None."""
    got = api("GET", f"{R}/actions/workflows/{workflow}/runs?head_sha={sha}&event=pull_request&per_page=100") or {}
    return max(got.get("workflow_runs", []), key=lambda x: x["id"], default=None)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {args[0]} failed: {r.stderr.strip()}")
    return r.stdout


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
    issues = inbox_issues()
    for path in out.splitlines():
        id_ = os.path.basename(path)[:-3]
        if os.path.dirname(path) + "/" != OPEN_DIR or not FILENAME_RE.match(id_ + ".md"):
            continue
        if id_ in issues:
            print(f"{id_}: issue exists")
            continue
        text = git("show", f"{after}:{path}")
        try:
            title, body = issue_for(id_, text, path)
        except ValueError as e:
            print(f"::warning title=intent-inbox::{path}: {e}")
            continue
        issue = issues[id_] = api("POST", f"{R}/issues", {"title": title, "body": body, "labels": [LABEL]})
        print(f"{id_}: opened {issue['html_url']}")
        if assignees and checks_of(text):
            r = api("POST", f"{R}/issues/{issue['number']}/assignees", {"assignees": assignees}, soft=True)
            if not (r and r.get("assignees")):
                print(f"::warning title=intent-inbox::Could not assign #{issue['number']} to {', '.join(assignees)}. "
                      "Copilot coding agent needs a user token in `token:` (see README).")


def cmd_intake():
    n, head = os.environ["PR_NUMBER"], os.environ["HEAD_SHA"]
    pr = api("GET", f"{R}/pulls/{n}")
    changed = [f["filename"] for f in pr_files(pr) if f["filename"].startswith(OPEN_DIR)]
    if not changed:
        return print(f"no changes to {OPEN_DIR}")
    who = approvers(pages(f"{R}/pulls/{n}/reviews"), head, (pr.get("user") or {}).get("login", ""))
    if who:
        return print(f"intake approved by {', '.join(who)}: {', '.join(changed)}")
    print(f"::error title=intent-intake::This PR changes {', '.join(changed)}. It needs an approving review on its "
          "latest commit from an owner, member or collaborator other than the PR author before it can merge.")
    return 1


def write_claims(found):
    claims = json.dumps([{"intent": k, "run": v} for k, v in sorted(found.items())])
    print(f"claims={claims}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"claims={claims}\n")


def cmd_claims():
    rid, found = os.environ.get("RUN_ID", ""), {}
    if rid:
        run = api("GET", f"{R}/actions/runs/{rid}")
        if run["conclusion"] == "success" and run["event"] == "pull_request":
            pr = pr_at(run["head_sha"])
            id_ = claim_of(pr and pr["body"])
            if id_:
                found[id_] = run["id"]
    else:
        wf = os.environ.get("INBOX_WORKFLOW", "")
        if not wf:
            raise SystemExit("The claims sweep needs the `workflow` input: the file name of the CI workflow, "
                             "e.g. intent-check.yml.")
        for pr in pages(f"{R}/pulls?state=open"):
            id_ = claim_of(pr.get("body"))
            run = id_ and latest_run(wf, pr["head"]["sha"])
            if run and run["status"] == "completed" and run["conclusion"] == "success":
                found[id_] = min(found.get(id_, run["id"]), run["id"])  # the earliest passing claim goes first
    write_claims(found)
    return 0


def note_behind(n, sha, branch):
    mark = f"<!-- intent-inbox-behind: {sha} -->"
    if not any(mark in (c.get("body") or "") for c in pages(f"{R}/issues/{n}/comments")):
        api("POST", f"{R}/issues/{n}/comments", {"body": f"{mark}\nThis claim passed, but it's behind `{branch}`. "
                                                         "Update the branch. CI re-runs, and the inbox merges it "
                                                         "if it still passes."})
    print(f"#{n} is behind {branch}; waiting for an update")


def cmd_ship():
    run = api("GET", f"{R}/actions/runs/{os.environ['RUN_ID']}")
    if run["conclusion"] != "success" or run["event"] != "pull_request":
        return print("run did not pass on a pull_request event")
    sha = run["head_sha"]
    newest = latest_run(run["workflow_id"], sha)
    if newest and newest["id"] > run["id"]:
        return print("a newer run exists for this commit; it decides")
    pr = pr_at(sha)
    id_ = claim_of(pr and pr["body"])
    if not pr or not id_:
        return print(f"no open PR at {sha[:12]} with a Claims: line")
    n, branch = pr["number"], pr["base"]["repo"]["default_branch"]
    if pr["base"]["ref"] != branch:
        return print(f"#{n} does not target {branch}")
    issue = inbox_issues().get(id_)
    if not issue:
        return print(f"{id_} has no intent-open issue, so it can't be claimed")
    first, competitors = plan(pages(f"{R}/pulls?state=all&sort=updated&direction=desc"), id_, n)
    if not claimable(issue) or not first:
        return close(n, f"Closing: intent `{id_}` is closed (shipped or not planned), so it can't be claimed.")
    got = api("GET", f"{R}/contents/{OPEN_DIR}{id_}.md?ref={branch}")
    if not got:
        return print(f"{OPEN_DIR}{id_}.md is not on {branch}")
    text = base64.b64decode(got["content"]).decode("utf-8")
    if not checks_of(text):
        return print(f"{id_} has no check: lines, so it can't be claimed")
    full = api("GET", f"{R}/pulls/{n}")
    blocked = out_of_scope([f["filename"] for f in pr_files(full)], parse(text)[0].get("touches"),
                           protected(os.environ.get("INBOX_PROTECT", "")))
    if blocked:
        print(f"::warning title=intent-inbox::Not auto-merging #{n}: {', '.join(blocked)} outside touches: "
              "or under a protected path. A human can review and merge it.")
        return
    if full.get("mergeable_state") == "behind":
        return note_behind(n, sha, branch)
    merged = api("PUT", f"{R}/pulls/{n}/merge", {"merge_method": "squash", "sha": sha,
                                                  "commit_title": f"{pr['title']} (#{n})",
                                                  "commit_message": f"Intent: {id_}\nClaims: {id_}\nHead: {sha}"},
                 soft=True)
    if not merged:
        print(f"::warning title=intent-inbox::Could not merge #{n}. The next sweep retries.")
        return 1
    print(f"merged #{n} at {sha[:12]} for {id_}")
    for c in competitors:
        close(c, f"Closing: #{n} claimed `{id_}` and passed its checks first, so it was merged.")
    if issue["state"] == "open":
        api("POST", f"{R}/issues/{issue['number']}/comments", {"body": f"Shipped in #{n}: {pr['html_url']}"})
        api("POST", f"{R}/issues/{issue['number']}/labels", {"labels": [SHIPPED]})
        api("PATCH", f"{R}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    cmds = {"open": cmd_open, "intake": cmd_intake, "claims": cmd_claims, "ship": cmd_ship}
    if mode not in cmds:
        raise SystemExit(__doc__)
    sys.exit(cmds[mode]())
