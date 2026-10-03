#!/usr/bin/env python3
"""intent-inbox: turn .intent/open/ intents into claimable work.

Usage:
  python3 scripts/intent_inbox.py open   # on push to the default branch: one issue per intent added to .intent/open/
  python3 scripts/intent_inbox.py ship   # on workflow_run (completed): commit the move to .intent/shipped/ onto the
                                         # first passing claim's branch, re-run CI on it, squash-merge that exact SHA,
                                         # then close the competing claims and the issue

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, BEFORE and AFTER (open), RUN_ID (ship),
INBOX_ASSIGNEES (optional, comma-separated logins for new issues),
FORK_TOKEN (optional: pushes the move to the default branch after merging a fork claim).
Never checks out or runs pull request code. No dependencies beyond Python 3 and git.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intent_check import CLAIM_RE, FILENAME_RE, OPEN_DIR, SHIPPED_DIR, done_when_checks, parse  # noqa: E402

LABEL = "intent-open"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
R = f"/repos/{REPO}"
API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
FORK_TOKEN = os.environ.get("FORK_TOKEN", "")
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
               "The first claiming PR whose CI passes is squash-merged, the intent moves to `.intent/shipped/`, "
               "and the other claiming PRs are closed. The PR may only change paths inside `touches:`, "
               "and never `.intent/` or `.github/`.")
    else:
        how = (f"**This intent can't be claimed.** Its Done when has no `check:` lines, so CI can't prove a PR "
               f"done. Claiming PRs fail and nothing is auto-merged. Add a `check:` line to `{path}` first.")
    link = f"{SERVER}/{REPO}/blob/HEAD/{path}"
    return title, f"<!-- intent-inbox: {id_} -->\nIntent [`{id_}`]({link}) is open.\n\n{body}\n\n---\n\n{how}\n"


def out_of_scope(files, touches, moved=None):
    """Changed files that block an auto-merge: outside touches:, or under .intent/ or .github/.
    `moved` exempts exactly the open/ -> shipped/ rename of that intent, which only the ship job commits."""
    scope = touches if isinstance(touches, list) else []
    exempt = {f"{OPEN_DIR}{moved}.md", f"{SHIPPED_DIR}{moved}.md"} if moved else set()
    return [f for f in files if f not in exempt and (f.startswith((".intent/", ".github/"))
            or not any(f == t or f.startswith(t.rstrip("/") + "/") for t in scope))]


def plan(prs, id_, number):
    """(first, competitors) for PR `number` claiming id_. first is False once another claim was merged."""
    others = [p for p in prs if p["number"] != number and claim_of(p.get("body")) == id_]
    return not any(p.get("merged_at") for p in others), [p["number"] for p in others if p["state"] == "open"]


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


def redact(text):
    for t in (TOKEN, FORK_TOKEN):
        text = text.replace(t, "***") if t else text
    return text


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {args[0]} failed: {redact(r.stderr).strip()}")
    return r.stdout


def find_issue(id_, state):
    for i in api("GET", f"{R}/issues?labels={LABEL}&state={state}&per_page=100") or []:
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
        if find_issue(id_, "all"):
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


def commit_move(token, ref, id_, n, parent=None):
    """Commit the open/ -> shipped/ move on top of branch `ref` and push it. Returns (sha, error)."""
    src, dst = f"{OPEN_DIR}{id_}.md", f"{SHIPPED_DIR}{id_}.md"
    url = SERVER.replace("://", f"://x-access-token:{token}@", 1) + f"/{REPO}.git"
    git("fetch", "-q", url, ref)
    git("checkout", "-q", "-B", "intent-inbox-ship", "FETCH_HEAD")
    if parent and git("rev-parse", "HEAD").strip() != parent:
        return None, f"{ref} moved past {parent[:12]}"
    if not os.path.exists(src):
        return None, f"{src} is not on {ref}"
    os.makedirs(SHIPPED_DIR, exist_ok=True)
    git("mv", src, dst)
    with open(dst, encoding="utf-8") as f:
        text = re.sub(r"^status:\s*draft\s*$", "status: shipped", f.read(), count=1, flags=re.M)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)
    git("add", dst)
    git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-qm", f"Ship {id_}\n\nIntent: {id_}\nShipped-by: #{n}")
    r = subprocess.run(["git", "push", "-q", url, f"HEAD:refs/heads/{ref}"], capture_output=True, text=True)
    if r.returncode:
        return None, redact(r.stderr).strip()[:300]
    return git("rev-parse", "HEAD").strip(), ""


def rerun(workflow_id, ref, sha):
    """Re-run the CI workflow on the claim branch after the move commit (a GITHUB_TOKEN push triggers no run).
    Returns the run's conclusion and URL."""
    api("POST", f"{R}/actions/workflows/{workflow_id}/dispatches", {"ref": ref})
    for _ in range(60):
        time.sleep(15)
        runs = api("GET", f"{R}/actions/workflows/{workflow_id}/runs?head_sha={sha}&event=workflow_dispatch")["workflow_runs"]
        if runs and runs[0]["status"] == "completed":
            return runs[0]["conclusion"], runs[0]["html_url"]
    return "timed out", ""


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
    first, competitors = plan(api("GET", f"{R}/pulls?state=all&sort=updated&direction=desc&per_page=100"), id_, n)
    got = api("GET", f"{R}/contents/{OPEN_DIR}{id_}.md?ref={branch}")
    if not got or not first:
        return close(n, f"Closing: intent `{id_}` has already shipped.")
    text = base64.b64decode(got["content"]).decode("utf-8")
    if not checks_of(text):
        return print(f"{id_} has no check: lines, so it can't be claimed")
    touches = parse(text)[0].get("touches")
    blocked = out_of_scope([f["filename"] for f in api("GET", f"{R}/pulls/{n}/files?per_page=100")], touches)
    if blocked:
        print(f"::warning title=intent-inbox::Not auto-merging #{n}: {', '.join(blocked)} outside touches: "
              "or under .intent/ or .github/. A human can review and merge it.")
        return
    same_repo = (pr["head"]["repo"] or {}).get("full_name") == REPO
    if same_repo:  # the move lands inside the merge: commit it on the claim branch, re-run CI, merge that SHA
        sha, why = commit_move(TOKEN, pr["head"]["ref"], id_, n, parent=sha)
        if not sha:
            return print(f"::error title=intent-inbox::Could not commit the move onto #{n}: {why}") or 1
        conclusion, url = rerun(run["workflow_id"], pr["head"]["ref"], sha)
        if conclusion != "success":
            api("POST", f"{R}/issues/{n}/comments", {"body": f"Committed the move of `{id_}` to `.intent/shipped/`, "
                                                      f"but CI on that commit ended `{conclusion}` ({url}). Not merging."})
            return 1
        files = [f["filename"] for f in api("GET", f"{R}/pulls/{n}/files?per_page=100")]
        if out_of_scope(files, touches, moved=id_):
            return print(f"::error title=intent-inbox::#{n} changed after the move commit; not merging") or 1
    api("PUT", f"{R}/pulls/{n}/merge", {"merge_method": "squash", "sha": sha, "commit_title": f"{pr['title']} (#{n})",
                                         "commit_message": f"Intent: {id_}\nClaims: {id_}\nHead: {sha}"})
    print(f"merged #{n} at {sha[:12]} for {id_}")
    for c in competitors:
        close(c, f"Closing: #{n} claimed `{id_}` and passed its checks first, so it was merged.")
    issue = find_issue(id_, "open")
    if issue:
        api("POST", f"{R}/issues/{issue['number']}/comments", {"body": f"Shipped in #{n}."})
        api("PATCH", f"{R}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
    if same_repo:
        return 0
    why = "a fork branch can't take the move commit and no INTENT_INBOX_TOKEN is set"
    if FORK_TOKEN:
        for _ in range(2):
            moved, why = commit_move(FORK_TOKEN, branch, id_, n)
            if moved:
                return print(f"moved {id_} to {SHIPPED_DIR} on {branch}")
    api("POST", f"{R}/issues/{n}/comments", {"body": f"Merged. `{OPEN_DIR}{id_}.md` stays in `{OPEN_DIR}` because {why}. "
                                              f"Move it to `{SHIPPED_DIR}` by hand."})
    return 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("open", "ship"):
        raise SystemExit(__doc__)
    sys.exit(cmd_open() if mode == "open" else cmd_ship())
