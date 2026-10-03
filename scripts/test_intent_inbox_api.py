#!/usr/bin/env python3
"""Self-test for intent_inbox.py's GitHub paths (open, intake, claims, ship) against a fake API. No network."""
import base64
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intent_inbox as ib  # noqa: E402

ID, OTHER = "20261003-demo", "20261003-other"
INTENT = """---
id: 20261003-demo
status: draft
touches: [examples/inbox-demo/, scripts/]
---
# Greet

## Want
A greeting.

## Not
Nothing else.

## Done when
- It prints the line
  check: `sh examples/inbox-demo/greet.sh`
"""


def pr(n, sha, body="", state="open", user="dev", merged_at=None, changed=1, mergeable="clean"):
    return {"number": n, "state": state, "merged_at": merged_at, "body": body, "head": {"sha": sha},
            "base": {"ref": "main", "repo": {"default_branch": "main"}}, "user": {"login": user},
            "title": f"PR {n}", "html_url": f"https://x/pull/{n}", "changed_files": changed,
            "mergeable_state": mergeable}


def run(id_, sha, conclusion="success", event="pull_request"):
    return {"id": id_, "head_sha": sha, "conclusion": conclusion, "event": event, "status": "completed", "workflow_id": 7}


def issue(n, id_=ID, state="open"):
    return {"number": n, "state": state, "body": f"<!-- intent-inbox: {id_} -->\nx", "labels": [{"name": ib.LABEL}]}


def files(*names, status="modified"):
    return [{"filename": f, "status": status} for f in names]


def review(login, assoc, commit="h2", state="APPROVED"):
    return {"user": {"login": login, "type": "User"}, "state": state, "commit_id": commit, "author_association": assoc}


class FakeGitHub:
    """Routes api(method, path) to canned data, 100 items a page, and records every write."""

    def __init__(self, prs=(), files=None, issues=(), reviews=(), runs=(), comments=None, merge_ok=True):
        self.prs, self.files, self.issues, self.reviews = list(prs), files or {}, list(issues), list(reviews)
        self.runs, self.comments, self.merge_ok = {r["id"]: r for r in runs}, comments or {}, merge_ok
        self.contents = {f"{ib.OPEN_DIR}{ID}.md": INTENT}
        self.writes = []

    @staticmethod
    def page(items, q):
        n = int(q.get("page", 1))
        return items[(n - 1) * 100:n * 100]

    def __call__(self, method, path, data=None, soft=False):
        p, _, qs = path.partition("?")
        q = dict(x.split("=", 1) for x in qs.split("&") if x)
        assert p.startswith(ib.R), path
        p = p[len(ib.R):]
        if method != "GET":
            self.writes.append((method, p, data))
            if p.endswith("/merge"):
                return {"merged": True} if self.merge_ok else None
            return {"number": 99, "html_url": "https://x/issues/99"} if p == "/issues" else {}
        if p == "/issues":
            return self.page(self.issues, q)
        if p == "/pulls":
            return self.page([x for x in self.prs if q.get("state") == "all" or x["state"] == "open"], q)
        if p.startswith("/contents/"):
            text = self.contents.get(p[len("/contents/"):])
            return text and {"content": base64.b64encode(text.encode()).decode()}
        m = re.fullmatch(r"/(pulls|issues|actions/runs|actions/workflows)/([^/]+)(?:/(\w+))?", p)
        kind, key, sub = m.groups()
        if kind == "actions/workflows":
            return {"workflow_runs": [r for r in self.runs.values() if r["head_sha"] == q["head_sha"]]}
        if kind == "actions/runs":
            return self.runs[int(key)]
        if sub == "files":
            return self.page(self.files.get(int(key), []), q)
        if sub == "reviews":
            return self.page(self.reviews, q)
        if sub == "comments":
            return self.page(self.comments.get(int(key), []), q)
        return next(x for x in self.prs if x["number"] == int(key))

    def did(self, method, path):
        return [d for m, p, d in self.writes if m == method and p == path]


class Base(unittest.TestCase):
    def go(self, fn, gh, **env):
        with mock.patch.object(ib, "api", gh), mock.patch.dict(os.environ, env), \
                contextlib.redirect_stdout(io.StringIO()):
            return fn()


class Intake(Base):
    def gh(self, reviews=(), fs=None, changed=1):
        return FakeGitHub(prs=[pr(5, "h2", user="dev", changed=changed)], reviews=reviews,
                          files={5: fs if fs is not None else files(f"{ib.OPEN_DIR}{ID}.md", status="added")})

    def intake(self, gh):
        return self.go(ib.cmd_intake, gh, PR_NUMBER="5", HEAD_SHA="h2")

    def test_no_inbox_change_passes(self):
        self.assertIsNone(self.intake(self.gh(fs=files("src/a.py"))))

    def test_collaborator_approval_passes(self):
        self.assertIsNone(self.intake(self.gh([review("ann", "COLLABORATOR")])))

    def test_author_approval_fails(self):
        self.assertEqual(self.intake(self.gh([review("dev", "OWNER")])), 1)

    def test_outsider_approval_fails(self):
        self.assertEqual(self.intake(self.gh([review("eve", "NONE"), review("bob", "CONTRIBUTOR")])), 1)

    def test_approval_of_an_older_commit_fails(self):
        self.assertEqual(self.intake(self.gh([review("ann", "MEMBER", commit="h1")])), 1)

    def test_changing_an_open_intent_needs_approval(self):
        self.assertEqual(self.intake(self.gh(fs=files(f"{ib.OPEN_DIR}{ID}.md"))), 1)

    def test_reads_every_page_of_files(self):
        fs = files(*[f"src/{i}.py" for i in range(150)])
        fs[120] = {"filename": f"{ib.OPEN_DIR}{ID}.md", "status": "added"}
        self.assertEqual(self.intake(self.gh(fs=fs, changed=150)), 1)

    def test_more_than_3000_files_fails(self):
        with self.assertRaises(SystemExit):
            self.intake(self.gh(changed=3001))


class Open(Base):
    def test_opens_one_issue_per_new_intent_and_skips_existing(self):
        old = "20261002-old"
        gh = FakeGitHub(issues=[issue(i, f"20261001-x{i}") for i in range(130)] + [issue(200, old)])
        out = {"diff": f"{ib.OPEN_DIR}{ID}.md\n{ib.OPEN_DIR}{old}.md\n", "show": INTENT}
        with mock.patch.object(ib, "git", lambda *a: out[a[0]]):
            self.go(ib.cmd_open, gh, BEFORE="a" * 40, AFTER="b" * 40)
        made = gh.did("POST", "/issues")
        self.assertEqual(len(made), 1)
        self.assertIn(f"[{ID}]", made[0]["title"])
        self.assertEqual(made[0]["labels"], [ib.LABEL])


class Claims(Base):
    def claims(self, gh, **env):
        with tempfile.NamedTemporaryFile("r+", suffix=".out") as f:
            self.go(ib.cmd_claims, gh, GITHUB_OUTPUT=f.name, **env)
            line = [x for x in f.read().splitlines() if x.startswith("claims=")][-1]
            return json.loads(line[len("claims="):])

    def test_workflow_run_reports_its_claim(self):
        gh = FakeGitHub(prs=[pr(3, "s1", f"Claims: {ID}")], runs=[run(5, "s1")])
        self.assertEqual(self.claims(gh, RUN_ID="5"), [{"intent": ID, "run": 5}])

    def test_failed_run_reports_nothing(self):
        gh = FakeGitHub(prs=[pr(3, "s1", f"Claims: {ID}")], runs=[run(5, "s1", "failure")])
        self.assertEqual(self.claims(gh, RUN_ID="5"), [])

    def test_sweep_keeps_the_earliest_passing_claim_per_intent(self):
        gh = FakeGitHub(prs=[pr(4, "s4", f"Claims: {ID}"), pr(3, "s3", f"Claims: {ID}"),
                             pr(5, "s5", f"Claims: {OTHER}"), pr(6, "s6", "no claim")],
                        runs=[run(40, "s4"), run(30, "s3"), run(50, "s5", "failure")])
        self.assertEqual(self.claims(gh, RUN_ID="", INBOX_WORKFLOW="ci.yml"), [{"intent": ID, "run": 30}])

    def test_sweep_uses_the_newest_run_of_a_commit(self):
        gh = FakeGitHub(prs=[pr(3, "s3", f"Claims: {ID}")], runs=[run(30, "s3"), run(31, "s3", "failure")])
        self.assertEqual(self.claims(gh, RUN_ID="", INBOX_WORKFLOW="ci.yml"), [])

    def test_sweep_reads_every_page_of_prs(self):
        prs = [pr(i, f"x{i}") for i in range(1, 121)]
        prs[110] = pr(111, "s111", f"Claims: {ID}")
        gh = FakeGitHub(prs=prs, runs=[run(9, "s111")])
        self.assertEqual(self.claims(gh, RUN_ID="", INBOX_WORKFLOW="ci.yml"), [{"intent": ID, "run": 9}])

    def test_sweep_needs_the_workflow(self):
        with self.assertRaises(SystemExit):
            self.claims(FakeGitHub(), RUN_ID="", INBOX_WORKFLOW="")


class Ship(Base):
    def gh(self, fs=("examples/inbox-demo/greet.sh",), iss=None, runs=None, extra=(), **kw):
        return FakeGitHub(prs=[pr(3, "s1", f"Claims: {ID}", mergeable=kw.pop("mergeable", "clean"),
                                  changed=len(fs)), pr(4, "s4", f"Claims: {ID}"), *extra],
                          files={3: files(*fs)}, issues=[iss or issue(10)], runs=runs or [run(5, "s1")], **kw)

    def ship(self, gh, protect=""):
        return self.go(ib.cmd_ship, gh, RUN_ID="5", INBOX_PROTECT=protect)

    def test_merges_the_passing_claim_and_closes_the_rest(self):
        gh = self.gh()
        self.assertEqual(self.ship(gh), 0)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge")[0]["sha"], "s1")
        self.assertEqual(gh.did("PATCH", "/pulls/4"), [{"state": "closed"}])
        self.assertEqual(gh.did("POST", "/issues/10/labels"), [{"labels": [ib.SHIPPED]}])
        self.assertEqual(gh.did("PATCH", "/issues/10")[0]["state"], "closed")

    def test_a_closed_issue_is_not_claimable(self):
        gh = self.gh(iss=issue(10, state="closed"))
        self.ship(gh)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])
        self.assertEqual(gh.did("PATCH", "/pulls/3"), [{"state": "closed"}])

    def test_no_issue_no_merge(self):
        gh = self.gh(iss=issue(10, OTHER))
        self.ship(gh)
        self.assertEqual(gh.writes, [])

    def test_a_merged_claim_wins(self):
        gh = self.gh(extra=[pr(2, "s2", f"Claims: {ID}", state="closed", merged_at="2026-10-03T00:00:00Z")])
        self.ship(gh)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])

    def test_protected_paths_block_even_inside_touches(self):
        gh = self.gh(fs=("scripts/x.py",))
        self.ship(gh, protect="action.yml,inbox/,scripts/")
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])
        gh = self.gh(fs=("scripts/x.py",))
        self.ship(gh)
        self.assertEqual(len(gh.did("PUT", "/pulls/3/merge")), 1)

    def test_a_blocked_file_on_page_two_blocks(self):
        fs = [f"examples/inbox-demo/{i}" for i in range(150)]
        fs[140] = ".github/workflows/x.yml"
        gh = self.gh(fs=fs)
        self.ship(gh)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])

    def test_more_than_3000_files_never_merges(self):
        gh = self.gh()
        gh.prs[0]["changed_files"] = 3001
        with self.assertRaises(SystemExit):
            self.ship(gh)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])

    def test_behind_comments_once_and_waits(self):
        gh = self.gh(mergeable="behind")
        self.ship(gh)
        self.assertEqual(gh.did("PUT", "/pulls/3/merge"), [])
        self.assertEqual(len(gh.did("POST", "/issues/3/comments")), 1)
        gh2 = self.gh(mergeable="behind", comments={3: [{"body": gh.did("POST", "/issues/3/comments")[0]["body"]}]})
        self.ship(gh2)
        self.assertEqual(gh2.writes, [])

    def test_a_failed_merge_fails_the_job(self):
        gh = self.gh(merge_ok=False)
        self.assertEqual(self.ship(gh), 1)
        self.assertEqual(gh.did("PATCH", "/pulls/4"), [])

    def test_a_newer_run_decides(self):
        gh = self.gh(runs=[run(5, "s1"), run(6, "s1", "failure")])
        self.ship(gh)
        self.assertEqual(gh.writes, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
