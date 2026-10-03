#!/usr/bin/env python3
"""Self-test for bin/git-why. Builds throwaway git repos and asserts what `git why` prints."""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHY = os.path.join(ROOT, "bin", "git-why")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import intent_check  # noqa: E402
ENV = {**os.environ, "GIT_WHY_NO_GH": "1", "GIT_AUTHOR_DATE": "2026-10-01T00:00:00", "GIT_COMMITTER_DATE": "2026-10-01T00:00:00"}


def intent(id_, status="draft", extra="", want="Something."):
    return textwrap.dedent(f"""\
    ---
    id: {id_}
    status: {status}
    touches: [src/]
    {extra}
    ---
    # Title of {id_}

    ## Want
    {want}

    ## Not
    Nothing else.

    ## Done when
    - it works
    """)


class Repo:
    def __init__(self):
        self.d = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("README.md", "x\n")
        self.commit("root")

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.d, check=True, capture_output=True, text=True, env=ENV).stdout

    def write(self, p, t):
        f = os.path.join(self.d, p)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "w").write(t)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def merge(self, branch, msg):
        self.git("merge", "-q", "--no-ff", branch, "-m", msg)

    def why(self, *args, via_git=False):
        cmd = ["git", "why", *args] if via_git else [sys.executable, WHY, *args]
        env = {**ENV, "PATH": os.path.dirname(WHY) + os.pathsep + ENV.get("PATH", "")}
        r = subprocess.run(cmd, cwd=self.d, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr


cases = []


def case(name):
    def deco(fn):
        cases.append((name, fn))
        return fn
    return deco


def expect(res, code, *needles, absent=()):
    got, out = res
    problems = [f"exit {got} != {code}"] if got != code else []
    problems += [f"missing {n!r}" for n in needles if n not in out]
    problems += [f"unexpected {n!r}" for n in absent if n in out]
    return problems, out


@case("direct commit trailer")
def _(r):
    r.write(".intent/20261001-feature.md", intent("20261001-feature", want="Make it fast."))
    r.write("src/a.py", "a = 1\n")
    r.commit("Add feature\n\nIntent: 20261001-feature")
    return expect(r.why("src/a.py:1"), 0, "Intent     20261001-feature  (draft)", "Found via  commit trailer",
                  "Make it fast.", "Nothing else.", "- it works")


@case("file line form and `git why` via PATH")
def _(r):
    r.write(".intent/20261001-feature.md", intent("20261001-feature"))
    r.write("src/a.py", "a = 1\nb = 2\n")
    r.commit("Add feature\n\nIntent: 20261001-feature")
    return expect(r.why("src/a.py", "2", via_git=True), 0, "src/a.py:2", "20261001-feature")


@case("trailer only on the merge commit, PR number from merge subject")
def _(r):
    r.write(".intent/20261001-feature.md", intent("20261001-feature"))
    r.commit("Add intent\n\nIntent: 20261001-feature")
    r.git("checkout", "-q", "-b", "topic")
    r.write("src/a.py", "a = 1\n")
    r.commit("wip, no trailer")
    r.git("checkout", "-q", "main")
    r.merge("topic", "Merge #7: feature\n\nIntent: 20261001-feature")
    return expect(r.why("src/a.py:1"), 0, "20261001-feature", "trailer on merge", "PR         #7")


@case("trailer on another commit of the same PR")
def _(r):
    r.git("checkout", "-q", "-b", "topic")
    r.write(".intent/20261001-feature.md", intent("20261001-feature"))
    r.commit("Intent file\n\nIntent: 20261001-feature")
    r.write("src/a.py", "a = 1\n")
    r.commit("code without trailer")
    r.git("checkout", "-q", "main")
    r.merge("topic", "Merge pull request #9 from x/topic")
    return expect(r.why("src/a.py:1"), 0, "20261001-feature", "trailer on another commit merged by", "PR         #9")


@case("squash commit without trailer that adds the intent file")
def _(r):
    r.write(".intent/20261001-feature.md", intent("20261001-feature"))
    r.write("src/a.py", "a = 1\n")
    r.commit("Feature (#12)")
    return expect(r.why("src/a.py:1"), 0, "20261001-feature", "intent file added by this commit", "PR         #12")


@case("superseded chain is followed both ways")
def _(r):
    r.write(".intent/20261001-v1.md", intent("20261001-v1", "shipped"))
    r.write("src/a.py", "a = 1\n")
    r.commit("v1\n\nIntent: 20261001-v1")
    r.write(".intent/20261002-v2.md", intent("20261002-v2", "shipped", extra="supersedes: 20261001-v1"))
    r.write("src/b.py", "b = 1\n")
    r.commit("v2\n\nIntent: 20261002-v2")
    r.write(".intent/20261003-v3.md", intent("20261003-v3", "draft", extra="supersedes: 20261002-v2"))
    r.commit("v3\n\nIntent: 20261003-v3")
    p1, o1 = expect(r.why("src/a.py:1"), 0, "Intent     20261001-v1  (shipped)",
                    "Superseded by 20261002-v2 (shipped) -> 20261003-v3 (draft)", "Now        20261003-v3: Title of 20261003-v3")
    p2, o2 = expect(r.why("src/b.py:1"), 0, "Supersedes 20261001-v1", "Superseded by 20261003-v3 (draft)")
    return p1 + p2, o1 + o2


@case("renamed intent file (migrated id) is found on HEAD")
def _(r):
    r.write(".intent/0001-old.md", intent("0001"))
    r.write("src/a.py", "a = 1\n")
    r.commit("old\n\nIntent: 0001")
    r.git("mv", ".intent/0001-old.md", ".intent/20261001-old.md")
    r.write(".intent/20261001-old.md", intent("20261001-old"))
    r.commit("migrate to a date-slug id")
    return expect(r.why("src/a.py:1"), 0, "0001 (now 20261001-old)", "renamed from .intent/0001-old.md")


@case("no trailer anywhere degrades gracefully and shows the commit")
def _(r):
    r.write("src/a.py", "a = 1\n")
    r.commit("Plain commit\n\nJust a body.")
    return expect(r.why("src/a.py:1"), 1, "No Intent: trailer found", "Plain commit", "commit ", "Just a body.",
                  absent=("Traceback",))


@case("uncommitted line")
def _(r):
    r.write("README.md", "x\nnew\n")
    return expect(r.why("README.md:2"), 1, "not committed yet")


@case("bad input fails with a message, not a traceback")
def _(r):
    p1, o1 = expect(r.why("nope.py:3"), 2, "git why:", absent=("Traceback",))
    p2, o2 = expect(r.why("README.md:99"), 2, "git why:", absent=("Traceback",))
    p3, o3 = expect(r.why(), 2, "usage: git why", absent=("Traceback",))
    return p1 + p2 + p3, o1 + o2 + o3


@case("--json output")
def _(r):
    r.write(".intent/20261001-feature.md", intent("20261001-feature"))
    r.write("src/a.py", "a = 1\n")
    r.commit("Add feature (#3)\n\nIntent: 20261001-feature")
    code, out = r.why("--json", "src/a.py:1")
    try:
        d = json.loads(out)
    except ValueError:
        return ["output is not JSON"], out
    want = {"intent": "20261001-feature", "status": "draft", "pr": 3, "want": "Something.", "found_via": "commit trailer"}
    return [f"{k}={d.get(k)!r}, want {v!r}" for k, v in want.items() if d.get(k) != v] + ([f"exit {code}"] if code else []), out


@case("Claims: trailer and an intent in .intent/open/")
def _(r):
    r.write(".intent/open/20261003-demo.md", intent("20261003-demo", want="Open for claims."))
    r.commit("Open inbox intent")
    r.write("src/a.py", "a = 1\n")
    r.commit("Claim it (#5)\n\nClaims: 20261003-demo")
    return expect(r.why("src/a.py:1"), 0, "Intent     20261003-demo  (draft)", "File       .intent/open/20261003-demo.md",
                  "Open for claims.", absent=("not found",))


@case("examples/inbox-demo/greet.sh: an intent in .intent/shipped/ (replica of #26)")
def _(r):
    shipped = ".intent/shipped/20261003-inbox-demo.md"
    r.write(shipped, open(os.path.join(ROOT, shipped)).read())
    r.write("examples/inbox-demo/greet.sh", open(os.path.join(ROOT, "examples/inbox-demo/greet.sh")).read())
    r.commit("Inbox demo: greet (pass) (#26)\n\nIntent: 20261003-inbox-demo\nClaims: 20261003-inbox-demo")
    problems, out = expect(r.why("examples/inbox-demo/greet.sh:1"), 0, "20261003-inbox-demo  (shipped)",
                           "File       .intent/shipped/20261003-inbox-demo.md", "hello from the intent inbox")
    real = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True)
    if real.returncode == 0 and real.stdout.strip() == "false":  # full clone of this repo: check the real line too
        res = subprocess.run([sys.executable, WHY, "--no-gh", "examples/inbox-demo/greet.sh:1"], cwd=ROOT,
                             capture_output=True, text=True, env=ENV)
        p2, o2 = expect((res.returncode, res.stdout + res.stderr), 0, "File       .intent/shipped/20261003-inbox-demo.md")
        problems, out = problems + p2, out + o2
    return problems, out


@case("--init writes today's template, and the gate can parse it")
def _(r):
    iid = f"{datetime.date.today():%Y%m%d}-rate-limit-login"
    os.makedirs(os.path.join(r.d, "src"))
    code, out = r.why("--init", "rate-limit-login")
    path = os.path.join(r.d, ".intent", iid + ".md")
    problems = [f"exit {code}"] if code else []
    if not os.path.exists(path):
        return problems + ["no file written"], out
    text = open(path).read()
    problems += [f"missing {n!r}" for n in (f"id: {iid}", "status: draft", "# Rate limit login", "## Not", "check: `")
                 if n not in text]
    fm, _, sections = intent_check.parse(text)
    problems += [] if fm.get("touches") == ["src/"] and intent_check.done_when_checks(sections) else ["template doesn't parse"]
    p2, o2 = expect(r.why("--init", "rate-limit-login"), 2, "already exists")
    p3, o3 = expect(r.why("--init", "Bad Slug"), 2, "usage: git why --init")
    return problems + p2 + p3, out + o2 + o3


fails = 0
for name, fn in cases:
    problems, out = fn(Repo())
    fails += bool(problems)
    print(f"{'FAIL' if problems else 'ok  '} {name}")
    if problems:
        print(textwrap.indent("\n".join(problems) + "\n" + out, "    "))
print(f"\n{len(cases) - fails}/{len(cases)} git why cases behave as specified")
sys.exit(1 if fails else 0)
