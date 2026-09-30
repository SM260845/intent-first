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

    def check(self, body="", extra=()):
        bf = os.path.join(self.d, ".git", "body")
        open(bf, "w").write(body)
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY")}
        r = subprocess.run([sys.executable, CHECK, "--base", self.base, "--head", self.rev(),
                            "--pr-body-file", bf, "--run-checks", *extra], cwd=self.d, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr


cases = []


def case(name, expect):
    def deco(fn):
        cases.append((name, expect, fn))
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


fails = 0
for name, expect, fn in cases:
    r = Repo()
    res = fn(r) or ""
    body, extra = res if isinstance(res, tuple) else (res, [])
    code, out = r.check(body, extra)
    ok = code == expect
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} expect={'pass' if expect == 0 else 'fail'} got={'pass' if code == 0 else 'fail'}  {name}")
    if not ok:
        print(textwrap.indent(out, "    "))
print(f"\n{len(cases) - fails}/{len(cases)} cases behave as specified")
sys.exit(1 if fails else 0)
