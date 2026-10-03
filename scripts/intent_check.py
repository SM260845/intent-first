#!/usr/bin/env python3
"""intent-check: the one gate an intent-first repo needs.

A PR body line "Claims: <id>" claims an inbox intent in .intent/open/ (Intent Inbox).

Usage:
  python3 scripts/intent_check.py --base <sha> --head <sha> [--pr-body-file FILE] [--run-checks]
                                  [--touches warn|fail] [--strict-touches]

Exit 0 = pass, 1 = fail. Warnings are printed as GitHub annotations.
No dependencies beyond Python 3 and git.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

INTENT_DIR = ".intent/"
OPEN_DIR = INTENT_DIR + "open/"        # Intent Inbox: open for claims, added by humans only
SHIPPED_DIR = INTENT_DIR + "shipped/"  # Intent Inbox: moved here when a claim is merged
FILENAME_RE = re.compile(r"^(\d{8})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
STATUSES = {"draft", "shipped"}
REQUIRED_KEYS = ("id", "status", "touches")
REQUIRED_SECTIONS = ("Want", "Not", "Done when")
TRAILER_RE = re.compile(r"^\s*Intent:\s*`?([A-Za-z0-9._-]+)`?\s*$", re.M)
CLAIM_RE = re.compile(r"^\s*Claims:\s*`?([A-Za-z0-9._-]+)`?\s*$", re.M)

errors, warnings, notes = [], [], []
GH = os.environ.get("GITHUB_ACTIONS") == "true"
sys.stdout.reconfigure(line_buffering=True)


def annotate(kind, msg, path=None):
    """GitHub workflow command, escaped so '%' and newlines survive."""
    data = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    props = "title=intent-check"
    if path:
        esc = path.replace("%", "%25").replace(",", "%2C").replace(":", "%3A")
        props = f"file={esc},line=1," + props
    print(f"::{kind} {props}::{data}")


def err(msg, path=None):
    errors.append(msg)
    annotate("error", msg, path) if GH else print(f"ERROR: {msg}")


def warn(msg, path=None):
    warnings.append(msg)
    annotate("warning", msg, path) if GH else print(f"WARN:  {msg}")


def note(msg):
    notes.append(msg)
    print(f"::notice::{msg}" if GH else f"NOTE:  {msg}")


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def locate(rev, id_):
    """(path, text) of intent id_ at rev, in .intent/, .intent/open/ or .intent/shipped/."""
    for d in (INTENT_DIR, OPEN_DIR, SHIPPED_DIR):
        t = show(rev, f"{d}{id_}.md")
        if t is not None:
            return f"{d}{id_}.md", t
    return None, None


def parse(text):
    """Return (frontmatter dict, body str, section dict) or raise ValueError."""
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter (file must start with '---')")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    fm_raw, body = text[4:end], text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"bad frontmatter line: {line!r}")
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip()] = v
    sections, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur:
            sections[cur].append(line)
    return fm, body, sections


def done_when_checks(sections):
    """Bullets under 'Done when' and optional indented 'check: `cmd`' lines."""
    bullets = []
    for line in sections.get("Done when", []):
        if re.match(r"^[-*]\s+\S", line):
            bullets.append({"text": line[1:].strip(), "check": None})
        else:
            m = re.match(r"^\s+check:\s*`(.+)`\s*$", line)
            if m and bullets:
                bullets[-1]["check"] = m.group(1)
    return bullets


def validate(path, text):
    """Schema check. Returns frontmatter or None."""
    rel = path[len(INTENT_DIR):]
    if "/" in rel and not path.startswith((OPEN_DIR, SHIPPED_DIR)):
        err(f"{path}: intents live in {INTENT_DIR}, {OPEN_DIR} or {SHIPPED_DIR}", path)
        return None
    name = os.path.basename(rel)
    m = FILENAME_RE.match(name)
    if not m:
        err(f"{path}: filename must be YYYYMMDD-slug.md (e.g. 20260928-rate-limit-login.md)", path)
        return None
    try:
        datetime.datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        err(f"{path}: '{m.group(1)}' is not a real date", path)
    try:
        fm, body, sections = parse(text)
    except ValueError as e:
        err(f"{path}: {e}", path)
        return None
    for k in REQUIRED_KEYS:
        if not fm.get(k):
            err(f"{path}: frontmatter missing '{k}'", path)
    stem = name[:-3]
    if fm.get("id") and fm["id"] != stem:
        err(f"{path}: id '{fm['id']}' must equal filename '{stem}'", path)
    if fm.get("status") and fm["status"] not in STATUSES:
        err(f"{path}: status must be one of {sorted(STATUSES)}, got '{fm['status']}'", path)
    if "touches" in fm and not isinstance(fm["touches"], list):
        err(f"{path}: touches must be a list, e.g. [src/auth/, tests/auth/]", path)
    if not re.search(r"^#\s+\S", body, re.M):
        err(f"{path}: missing '# Title'", path)
    for s in REQUIRED_SECTIONS:
        content = [ln for ln in sections.get(s, []) if ln.strip()]
        if s not in sections:
            err(f"{path}: missing section '## {s}'", path)
        elif not content:
            err(f"{path}: section '## {s}' is empty", path)
    if "Done when" in sections and not done_when_checks(sections):
        err(f"{path}: '## Done when' needs at least one '- ' bullet", path)
    fm["_sections"] = sections
    return fm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--pr-body-file")
    ap.add_argument("--run-checks", action="store_true")
    ap.add_argument("--touches", choices=("warn", "fail"), default="warn",
                    help="what to do with changed paths outside the intent's touches: list")
    ap.add_argument("--strict-touches", dest="touches", action="store_const", const="fail",
                    help="same as --touches=fail")
    a = ap.parse_args()

    base = git("merge-base", a.base, a.head).strip()
    diff = git("diff", "--name-status", "--no-renames", base, a.head).splitlines()
    changes = [(ln.split("\t", 1)[0][0], ln.split("\t", 1)[1]) for ln in diff if ln.strip()]
    intent_changes = [(s, p) for s, p in changes if p.startswith(INTENT_DIR)]
    code_paths = [p for s, p in changes if not p.startswith(INTENT_DIR)]

    print(f"base {base[:12]}  head {a.head[:12]}  files changed: {len(changes)}")

    # --- 1. schema of every intent file this PR adds or modifies
    added, modified, inbox = {}, {}, {}
    for status, path in intent_changes:
        stem = os.path.basename(path)
        stem = stem[:-3] if stem.endswith(".md") else stem
        if status == "D":
            if path.startswith(OPEN_DIR) and ("A", f"{SHIPPED_DIR}{stem}.md") in intent_changes:
                note(f"{stem}: moved from {OPEN_DIR} to {SHIPPED_DIR}")
            else:
                err(f"{path}: deleting intents is not allowed. Intents are a log; supersede instead.", path)
            continue
        text = show(a.head, path) or ""
        fm = validate(path, text)
        if path.startswith(OPEN_DIR):
            inbox[stem] = (path, fm)
        else:
            (added if status == "A" else modified)[stem] = (path, fm)

    # --- 3. immutability: shipped intents cannot change at all
    for stem, (path, fm) in modified.items():
        old = show(base, path)
        old_fm = parse_safe(old)
        if old_fm and old_fm.get("status") == "shipped":
            err(f"{path}: intent is shipped and immutable. Write a new intent with 'supersedes: {stem}'.", path)
        elif old_fm and fm and old_fm.get("status") == "draft":
            if fm.get("status") == "shipped":
                note(f"{stem}: status flip draft -> shipped")

    # --- gate: collect referenced intent ids
    refs, body = set(), ""
    if a.pr_body_file and os.path.exists(a.pr_body_file):
        body = open(a.pr_body_file, encoding="utf-8").read()
        refs |= set(TRAILER_RE.findall(body))
    log = git("log", "--format=%B%x00", f"{base}..{a.head}")
    refs |= set(TRAILER_RE.findall(log))

    for r in sorted(refs - set(added)):
        base_text = locate(base, r)[1]
        base_fm = parse_safe(base_text)
        head_text = locate(a.head, r)[1]
        if base_fm is None and head_text is None:
            err(f"Intent: {r} does not exist in .intent/")
        elif base_fm is not None and base_fm.get("status") == "shipped":
            err(f"Intent: {r} is already shipped. Reference a draft intent, or add a new one (use 'supersedes:' to replace it).")

    # --- Intent Inbox: "Claims: <id>" takes an intent from .intent/open/ and must run its checks
    claims, claim_fm = set(CLAIM_RE.findall(body)), None
    if len(claims) > 1:
        err(f"One PR, one claim. This PR claims {len(claims)}: {', '.join(sorted(claims))}")
    for c in sorted(claims)[:1]:
        if any(p.startswith(OPEN_DIR) for _, p in changes):
            err(f"A PR that claims an intent can't change {OPEN_DIR}. Only humans add intents there.")
        text = show(base, f"{OPEN_DIR}{c}.md")
        if text is None:
            where = locate(base, c)[0]
            err(f"Claims: {c} is not open" + (f" (it is at {where})." if where else f": {OPEN_DIR}{c}.md does not exist on the base branch."))
            continue
        claim_fm = validate(f"{OPEN_DIR}{c}.md", text)
        if claim_fm and not any(b["check"] for b in done_when_checks(claim_fm["_sections"])):
            err(f"Claims: {c} can't be claimed. Its Done when has no check: lines, so CI can't prove a PR done.")
        if not a.run_checks:
            err(f"Claims: {c} needs its check: lines to run, and they were skipped (fork PR or run-checks: false).")

    ids = set(added) | set(modified) | refs | claims
    # --- 1. the gate: exactly ONE intent
    if len(ids) == 0 and inbox:
        note(f"Adds or edits inbox intents only: {', '.join(sorted(inbox))}")
    elif len(ids) == 0:
        err("No intent. Add one .intent/YYYYMMDD-slug.md, or reference an existing draft with an 'Intent: <id>' line in the PR body or a commit trailer.")
    elif len(ids) > 1:
        err(f"One PR, one intent. This PR references {len(ids)}: {', '.join(sorted(ids))}")
    intent_id = next(iter(ids)) if len(ids) == 1 else None

    # --- 5. supersedes
    for stem, (path, fm) in added.items():
        if not fm or not fm.get("supersedes"):
            continue
        old = fm["supersedes"]
        old_path = f"{INTENT_DIR}{old}.md"
        old_fm = parse_safe(show(base, old_path))
        if old_fm is None:
            err(f"{path}: supersedes '{old}' but {old_path} does not exist on the base branch", path)
        else:
            if old_fm.get("status") != "shipped":
                warn(f"{path}: supersedes '{old}', which is still '{old_fm.get('status')}'. Consider editing the draft instead.", path)
            if any(p == old_path for _, p in intent_changes):
                err(f"{old_path}: a superseded intent must stay untouched. The new intent records the replacement.", old_path)
            else:
                note(f"{stem} supersedes {old} (old file untouched)")

    # resolve the intent's frontmatter for touches/checks
    fm = None
    if intent_id:
        if intent_id in added:
            fm = added[intent_id][1]
        elif intent_id in modified:
            fm = modified[intent_id][1]
        elif intent_id in claims:
            fm = claim_fm
        else:
            p, t = locate(a.head, intent_id)
            fm = validate(p, t) if t else None

    # --- 8. touches: warn (or, with --touches=fail, fail) on paths outside scope
    if fm and isinstance(fm.get("touches"), list):
        scope = fm["touches"]
        outside = [p for p in code_paths if not any(p == t or p.startswith(t.rstrip("/") + "/") for t in scope)]
        for p in outside:
            (err if a.touches == "fail" else warn)(f"{p} is outside touches {scope} of intent {intent_id}", p)

    # --- 7. Done-when checks
    if fm and fm.get("_sections"):
        bullets = done_when_checks(fm["_sections"])
        for b in bullets:
            if not b["check"]:
                note(f"Done when (human review): {b['text']}")
            elif a.run_checks and not errors:
                print(f"--- check: {b['check']}", flush=True)
                r = subprocess.run(b["check"], shell=True)
                if r.returncode != 0:
                    err(f"Done-when check failed ({r.returncode}): {b['check']}")
                else:
                    print(f"    ok: {b['text']}")
            else:
                note(f"Done when (check, not run): {b['check']}")

    print()
    if intent_id:
        print(f"Intent: {intent_id}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## intent-check: {'❌ FAIL' if errors else '✅ PASS'}\n\n")
            f.write(f"**Intent:** `{intent_id or 'none'}`")
            if fm and fm.get("_sections"):
                title = re.search(r"^#\s+(.+)$", locate(a.head, intent_id)[1] or "", re.M)
                f.write(f" ({title.group(1).strip()})" if title else "")
            f.write(f"  \n**Touches mode:** {a.touches}\n\n")
            for label, items in (("Error", errors), ("Warning", warnings), ("Note", notes)):
                for i in items:
                    f.write(f"- **{label}:** {i}\n")
            if errors:
                f.write("\n**How to fix:** add exactly one `.intent/YYYYMMDD-slug.md` with frontmatter "
                        "(`id`, `status`, `touches`) and non-empty `## Want`, `## Not`, `## Done when` sections, "
                        "or reference an existing draft with an `Intent: <id>` line in the PR body or a commit trailer. "
                        "Rules: https://github.com/ao3575911/intent-first#rules\n")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            valid_id = intent_id and FILENAME_RE.match(f"{intent_id}.md")
            f.write(f"intent={intent_id if valid_id else ''}\n")
    return 1 if errors else 0


def parse_safe(text):
    if text is None:
        return None
    try:
        return parse(text)[0]
    except ValueError:
        return {}


if __name__ == "__main__":
    sys.exit(main())
