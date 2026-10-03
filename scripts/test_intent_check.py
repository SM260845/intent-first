#!/usr/bin/env python3
"""Self-test for intent_check.py. Builds throwaway git repos and asserts pass/fail."""
import os
import subprocess
import sys
import tempfile
import textwrap

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intent_check.py")


def intent(id_, status="draft", touches="[src/]", extra="", want="Something.", done="- it works\n"):
    return textwrap.dedent(f"""\
    ---
    id: {id_}
    status: {status}
    touches: {touches}
    {extra}
    ---
    # Title

    ## Want
    {want}

    ## Not
    Nothing else.

    ## Done when
    """) + done


class Repo:
    def __init__(self):
        self.d = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("README.md", "x\n")
        self.write(".intent/20260101-base.md", intent("20260101-base", "shipped", "[README.md]"))
        self.commit("base")
        self.base = self.rev()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.d, check=True, capture_output=True, text=True).stdout

    def write(self, p, t):
        f = os.path.join(self.d, p)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "w").write(t)

    def rm(self, p):
        self.git("rm", "-q", p)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def rev(self):
        return self.git("rev-parse", "HEAD").strip()

    def check(self, body="", extra=(), output=None):
        bf = os.path.join(self.d, ".git", "body")
        open(bf, "w").write(body)
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT")}
        if output:
            env["GITHUB_OUTPUT"] = output
        r = subprocess.run([sys.executable, CHECK, "--base", self.base, "--head", self.rev(),
                            "--pr-body-file", bf, "--run-checks", *extra], cwd=self.d, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr


cases = []


def case(name, expect, contains=""):
    def deco(fn):
        cases.append((name, expect, contains, fn))
        return fn
    return deco


@case("new valid intent + code", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature"))
    r.write("src/a.py", "print(1)\n")
    r.commit("add")


@case("junk intent 'hi' (kill criterion S4)", 1)
def _(r):
    r.write(".intent/hi.md", "hi\n")
    r.commit("hi")


@case("junk intent 'hi' with no extension", 1)
def _(r):
    r.write(".intent/hi", "hi\n")
    r.commit("hi")


@case("valid filename, junk body", 1)
def _(r):
    r.write(".intent/20260928-hi.md", "hi\n")
    r.commit("hi")


@case("id does not match filename", 1)
def _(r):
    r.write(".intent/20260928-feature.md", intent("0042"))
    r.commit("x")


@case("missing Not section", 1)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature").replace("## Not\nNothing else.\n", ""))
    r.commit("x")


@case("code only, no intent", 1)
def _(r):
    r.write("src/a.py", "print(1)\n")
    r.commit("x")


@case("two new intents", 1)
def _(r):
    r.write(".intent/20260928-a.md", intent("20260928-a"))
    r.write(".intent/20260928-b.md", intent("20260928-b"))
    r.commit("x")


@case("reference existing draft via commit trailer", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature"))
    r.commit("draft")
    r.base = r.rev()
    r.write("src/a.py", "print(2)\n")
    r.commit("more\n\nIntent: 20260928-feature")


@case("reference existing draft via PR body + status flip", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature"))
    r.commit("draft")
    r.base = r.rev()
    r.write(".intent/20260928-feature.md", intent("20260928-feature", status="shipped"))
    r.commit("ship")
    return "Intent: 20260928-feature"


@case("reference a shipped intent", 1)
def _(r):
    r.write("README.md", "y\n")
    r.commit("x\n\nIntent: 20260101-base")


@case("reference unknown intent", 1)
def _(r):
    r.write("src/a.py", "x\n")
    r.commit("x\n\nIntent: 20260928-nope")


@case("edit shipped intent body", 1)
def _(r):
    r.write(".intent/20260101-base.md", intent("20260101-base", "shipped", "[README.md]", want="Changed."))
    r.commit("x")


@case("delete shipped intent", 1)
def _(r):
    r.rm(".intent/20260101-base.md")
    r.commit("x")


@case("supersede, old untouched", 0)
def _(r):
    r.write(".intent/20260928-v2.md", intent("20260928-v2", "shipped", "[README.md]", extra="supersedes: 20260101-base"))
    r.write("README.md", "v2\n")
    r.commit("x")


@case("supersede but also edit old", 1)
def _(r):
    r.write(".intent/20260928-v2.md", intent("20260928-v2", extra="supersedes: 20260101-base"))
    r.write(".intent/20260101-base.md", intent("20260101-base", "shipped", "[README.md]", want="Edited."))
    r.commit("x")


@case("supersede unknown id", 1)
def _(r):
    r.write(".intent/20260928-v2.md", intent("20260928-v2", extra="supersedes: 20250101-ghost"))
    r.commit("x")


def archive_base(r):
    r.write(".intent/shipped/20260101-base.md", intent("20260101-base", "shipped", "[README.md]"))
    r.rm(".intent/20260101-base.md")
    r.commit("archive")
    r.base = r.rev()


@case("supersede archived intent, old untouched", 0,
      contains="20260928-v2 supersedes 20260101-base (old file untouched)")
def _(r):
    archive_base(r)
    r.write(".intent/20260928-v2.md", intent("20260928-v2", "shipped", "[README.md]", extra="supersedes: 20260101-base"))
    r.write("README.md", "v2\n")
    r.commit("x")


@case("supersede archived intent but also edit old", 1,
      contains=".intent/shipped/20260101-base.md: a superseded intent must stay untouched.")
def _(r):
    archive_base(r)
    r.write(".intent/20260928-v2.md", intent("20260928-v2", extra="supersedes: 20260101-base"))
    r.write(".intent/shipped/20260101-base.md", intent("20260101-base", "shipped", "[README.md]", want="Edited."))
    r.commit("x")


@case("failing check: line", 1)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", done="- fails\n  check: `false`\n"))
    r.commit("x")


@case("passing check: line", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", done="- passes\n  check: `true`\n"))
    r.commit("x")


@case("path outside touches only warns", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="[src/]"))
    r.write("docs/elsewhere.md", "x\n")
    r.commit("x")


@case("path outside touches fails with --touches=fail", 1)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="[src/]"))
    r.write("docs/elsewhere.md", "x\n")
    r.commit("x")
    return "", ["--touches=fail"]


@case("path outside touches fails with --strict-touches", 1)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="[src/]"))
    r.write("docs/elsewhere.md", "x\n")
    r.commit("x")
    return "", ["--strict-touches"]


@case("paths inside touches pass with --strict-touches", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="[src/]"))
    r.write("src/a.py", "x\n")
    r.commit("x")
    return "", ["--strict-touches"]


def inbox(r, done="- ok exists\n  check: `test -f src/ok`\n"):
    """Put an open inbox intent on the base branch."""
    r.write(".intent/open/20261003-demo.md", intent("20261003-demo", done=done))
    r.commit("open")
    r.base = r.rev()


@case("claim: inbox intent's checks pass", 0)
def _(r):
    inbox(r)
    r.write("src/ok", "x\n")
    r.commit("x")
    return "Claims: 20261003-demo"


@case("claim: inbox intent's checks fail", 1)
def _(r):
    inbox(r)
    r.write("src/other", "x\n")
    r.commit("x")
    return "Claims: 20261003-demo"


@case("claim: intent without check: lines can't be claimed", 1)
def _(r):
    inbox(r, done="- it works\n")
    r.write("src/ok", "x\n")
    r.commit("x")
    return "Claims: 20261003-demo"


@case("claim: PR that changes .intent/open/ is rejected", 1)
def _(r):
    inbox(r)
    r.write("src/ok", "x\n")
    r.write(".intent/open/20261003-more.md", intent("20261003-more"))
    r.commit("x")
    return "Claims: 20261003-demo"


@case("claim: PR that adds its own intent is rejected", 1)
def _(r):
    inbox(r)
    r.write("src/ok", "x\n")
    r.write(".intent/20261003-feature.md", intent("20261003-feature"))
    r.commit("x")
    return "Claims: 20261003-demo"


@case("inbox: editing a merged open intent", 1)
def _(r):
    inbox(r)
    r.write(".intent/open/20261003-demo.md", intent("20261003-demo", want="Something else."))
    r.commit("edit")


@case("claim: intent not in .intent/open/", 1)
def _(r):
    r.write("src/ok", "x\n")
    r.commit("x")
    return "Claims: 20261003-demo"


@case("inbox: human adds an open intent only", 0)
def _(r):
    r.write(".intent/open/20261003-demo.md", intent("20261003-demo"))
    r.commit("open")


@case("inbox: own intent plus an open intent", 0)
def _(r):
    r.write(".intent/20261003-feature.md", intent("20261003-feature"))
    r.write(".intent/open/20261003-demo.md", intent("20261003-demo"))
    r.commit("x")


@case("inbox: open intents are immutable, so they can't move to shipped/", 1)
def _(r):
    inbox(r)
    r.write(".intent/shipped/20261003-demo.md", open(os.path.join(r.d, ".intent/open/20261003-demo.md")).read())
    r.rm(".intent/open/20261003-demo.md")
    r.write("src/ok", "x\n")
    r.commit("ship")


@case("inbox: own intent plus a move is rejected", 1)
def _(r):
    inbox(r)
    r.write(".intent/20261003-feature.md", intent("20261003-feature"))
    r.write(".intent/shipped/20261003-demo.md", open(os.path.join(r.d, ".intent/open/20261003-demo.md")).read())
    r.rm(".intent/open/20261003-demo.md")
    r.commit("x")


@case("inbox: deleting an open intent without shipping it", 1)
def _(r):
    inbox(r)
    r.rm(".intent/open/20261003-demo.md")
    r.commit("rm")


@case("intents outside .intent/, open/ and shipped/ are rejected", 1)
def _(r):
    r.write(".intent/misc/20261003-demo.md", intent("20261003-demo"))
    r.commit("x")


# --- skipping the gate: exempt-authors, skip-label, exempt-paths
BOTS = "--exempt-authors=dependabot[bot],renovate[bot]"


@case("exempt author (dependabot) with no intent passes with a notice", 0, "Skipped: the author dependabot[bot]")
def _(r):
    r.write("requirements.txt", "requests==2.32.4\n")
    r.commit("Bump requests")
    return "", ["--author=dependabot[bot]", BOTS]


@case("a human author not in exempt-authors still needs an intent", 1, "No intent")
def _(r):
    r.write("requirements.txt", "requests==2.32.4\n")
    r.commit("Bump requests")
    return "", ["--author=someone", BOTS]


@case("skip-label on the PR passes with a notice", 0, "label (skip-label)")
def _(r):
    r.write("src/a.py", "print(1)\n")
    r.commit("typo")
    return "", ["--skip-label=no-intent", '--labels=["docs", "No-Intent"]']


@case("a different label doesn't skip", 1, "No intent")
def _(r):
    r.write("src/a.py", "print(1)\n")
    r.commit("typo")
    return "", ["--skip-label=no-intent", "--labels=docs,bug"]


@case("exempt-paths: only matching files changed passes", 0, "every changed file matches exempt-paths")
def _(r):
    r.write("README.md", "typo fixed\n")
    r.write("docs/guide/setup.md", "x\n")
    r.commit("docs")
    return "", ["--exempt-paths=**/*.md"]


@case("exempt-paths: one file outside the globs needs an intent", 1, "No intent")
def _(r):
    r.write("docs/setup.md", "x\n")
    r.write("src/a.py", "print(1)\n")
    r.commit("docs and code")
    return "", ["--exempt-paths=docs/\n*.md"]


@case("exempt-paths: * stays inside one folder", 1, "No intent")
def _(r):
    r.write("docs/deep/setup.txt", "x\n")
    r.commit("docs")
    return "", ["--exempt-paths=docs/*.txt"]


@case("exemptions never skip a PR that changes .intent/", 1, "Not skipping")
def _(r):
    r.write(".intent/20260101-base.md", intent("20260101-base", "shipped", "[README.md]", want="Changed."))
    r.commit("edit shipped")
    return "", ["--author=dependabot[bot]", BOTS]


# --- forgiving parsing
@case("touches: as a YAML block list", 0)
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="X").replace("touches: X", "touches:\n  - src/\n  - 'tests/'"))
    r.write("src/a.py", "print(1)\n")
    r.write("tests/t.py", "print(1)\n")
    r.commit("add")
    return "", ["--touches=fail"]


@case("a YAML block list for touches: is still enforced", 1, "outside touches ['src/']")
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="X").replace("touches: X", "touches:\n- src/"))
    r.write("lib/a.py", "print(1)\n")
    r.commit("add")
    return "", ["--touches=fail"]


@case("a list item under a plain value says how to write lists", 1, "write lists as [src/, tests/]")
def _(r):
    r.write(".intent/20260928-feature.md", intent("20260928-feature", touches="X").replace("touches: X", "touches: src/\n  - tests/"))
    r.commit("add")


@case("section headings match regardless of case", 0)
def _(r):
    t = intent("20260928-feature").replace("## Want", "## WANT").replace("## Done when", "## Done When")
    r.write(".intent/20260928-feature.md", t)
    r.write("src/a.py", "print(1)\n")
    r.commit("add")


fails = 0
for name, expect, contains, fn in cases:
    r = Repo()
    res = fn(r) or ""
    body, extra = res if isinstance(res, tuple) else (res, [])
    code, out = r.check(body, extra)
    ok = code == expect and contains in out
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} expect={'pass' if expect == 0 else 'fail'} got={'pass' if code == 0 else 'fail'}  {name}")
    if not ok:
        print(textwrap.indent(out, "    "))


def output_case(name, body, want):
    """The action's `intent` output: set only for an intent that exists."""
    global fails
    r = Repo()
    r.write("src/a.py", "print(1)\n")
    r.commit("code")
    out = os.path.join(r.d, ".git", "output")
    r.check(body, output=out)
    got = open(out).read().strip()
    ok = got == f"intent={want}"
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} output {got!r}  {name}")


output_case("output: an existing intent id is set", "Intent: 20260101-base", "20260101-base")
output_case("output: a typo'd intent id is not set", "Intent: 20260101-bsae", "")
total = len(cases) + 2
print(f"\n{total - fails}/{total} cases behave as specified")
sys.exit(1 if fails else 0)
