#!/usr/bin/env python3
"""proof-check: verify proof bundles in a proof-carrying PR.

A proof bundle (.proof/<intent-id>.json) is written by
`agent-session-recorder bundle <session> --intent <id>`. It holds the sealed
agent session, its Merkle batches (optionally RFC 3161 timestamped), and a
`proof.link` event naming the intent and the commit the session produced.

This is an independent, dependency-free re-implementation of the recorder's
`verify`, so the PR is checked without trusting the tool that wrote it.

Checks per bundle:
  1. the bundle names an intent that exists in .intent/
  2. the hash chain is intact (no event edited, dropped, inserted or reordered)
  3. every event is covered by a Merkle batch; batch roots and links match;
     any RFC 3161 token covers its batch root
  4. the sealed proof.link event matches the bundle's intent and commit
     (so a proof can't be borrowed from another intent)
  5. the linked commit is in this PR, and nothing but .proof/ or .intent/
     changed after it (so code can't be swapped in after the session)

PRs without a bundle pass with a notice: they are treated as human-authored.
"""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys

GENESIS = "0" * 64
SHA256_OID = bytes.fromhex("0609608648016503040201")


def canonical(v):
    """Match the recorder's canonical JSON (sorted keys, no spaces, JS number format)."""
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (int, float, str)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(canonical(x) for x in v) + "]"
    return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical(v[k]) for k in sorted(v)) + "}"


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def event_hash(e, prev):
    body = {k: x for k, x in e.items() if k != "seal"}
    return sha(prev + canonical(body))


def merkle_root(leaves):
    if not leaves:
        return sha(b"")
    level = [sha(b"\x00" + bytes.fromhex(h)) for h in leaves]
    while len(level) > 1:
        level = [sha(b"\x01" + bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1])) if i + 1 < len(level) else level[i]
                 for i in range(0, len(level), 2)]
    return level[0]


def check_tsr(tsr, root):
    i = tsr.find(b"\x02\x01")
    if i < 0 or i > 12:
        return "unparseable TSA response"
    if tsr[i + 2] > 1:
        return "TSA refused (status %d)" % tsr[i + 2]
    h = bytes.fromhex(root)
    if SHA256_OID + b"\x05\x00\x04\x20" + h in tsr or SHA256_OID + b"\x04\x20" + h in tsr:
        return None
    return "timestamp token does not cover this batch root"


def verify_bundle(b, name):
    """Content checks (1-4, minus the .intent/ lookup). Returns (errors, warnings)."""
    errors, warnings = [], []
    if b.get("v") != 1:
        return ["unsupported bundle version %r" % b.get("v")], warnings
    if b.get("intent") != name:
        errors.append("bundle intent %r does not match file name %r" % (b.get("intent"), name))
    prev, expect, hashes = GENESIS, 0, {}
    for i, e in enumerate(b.get("events", [])):
        s = e.get("seal")
        if not s:
            errors.append("event %d is not sealed" % i)
            continue
        if s["seq"] != expect:
            errors.append("event %d: seq %d, expected %d (missing, inserted or reordered)" % (i, s["seq"], expect))
        if s["prev"] != prev:
            errors.append("event %d: does not link to the previous event" % i)
        if event_hash(e, s["prev"]) != s["hash"]:
            errors.append("event %d (%s): content modified after sealing" % (i, e.get("type")))
        hashes[s["seq"]] = s["hash"]
        prev, expect = s["hash"], s["seq"] + 1
    prev_root, nxt, stamped = GENESIS, 0, 0
    for i, bt in enumerate(b.get("batches", [])):
        if bt["from"] != nxt:
            errors.append("batch %d starts at %d, expected %d" % (i, bt["from"], nxt))
        if bt["prevRoot"] != prev_root:
            errors.append("batch %d does not link to the previous batch" % i)
        leaves = [hashes.get(k) for k in range(bt["from"], bt["to"] + 1)]
        if None in leaves:
            errors.append("batch %d covers missing events" % i)
        elif merkle_root(leaves) != bt["root"]:
            errors.append("batch %d: Merkle root mismatch" % i)
        if bt.get("tsa"):
            err = check_tsr(base64.b64decode(bt["tsa"]["tsr"]), bt["root"])
            if err:
                errors.append("batch %d: %s" % (i, err))
            else:
                stamped += 1
        prev_root, nxt = bt["root"], bt["to"] + 1
    if nxt < expect:
        errors.append("%d event(s) are not covered by a Merkle batch" % (expect - nxt))
    if not stamped:
        warnings.append("no RFC 3161 timestamp; the chain is only locally sealed")
    links = [e for e in b.get("events", []) if e.get("type") == "note" and (e.get("payload") or {}).get("kind") == "proof.link"]
    if not links:
        errors.append("no sealed proof.link event")
    else:
        p = links[-1]["payload"]
        if p.get("intent") != b.get("intent") or p.get("commit") != b.get("commit"):
            errors.append("sealed proof.link (%s @ %s) does not match bundle (%s @ %s)"
                          % (p.get("intent"), str(p.get("commit"))[:12], b.get("intent"), str(b.get("commit"))[:12]))
    return errors, warnings


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    a = ap.parse_args()
    changed = [p for p in git("diff", "--name-only", "--diff-filter=AM", a.base, a.head).splitlines()
               if p.startswith(".proof/") and p.endswith(".json")]
    if not changed:
        print("::notice::no proof bundle in this PR; treated as human-authored")
        return 0
    pr_commits = set(git("rev-list", "%s..%s" % (a.base, a.head)).splitlines())
    failed = False
    for path in changed:
        name = os.path.basename(path)[:-5]
        b = json.loads(git("show", "%s:%s" % (a.head, path)))
        errors, warnings = verify_bundle(b, name)
        if subprocess.run(["git", "cat-file", "-e", "%s:.intent/%s.md" % (a.head, name)], capture_output=True).returncode:
            errors.append("no intent .intent/%s.md in this PR's head" % name)
        c = b.get("commit", "")
        if c not in pr_commits:
            errors.append("linked commit %s is not part of this PR" % c[:12])
        else:
            after = [p for p in git("diff", "--name-only", c, a.head).splitlines()
                     if not p.startswith((".proof/", ".intent/"))]
            if after:
                errors.append("code changed after the session's commit %s: %s" % (c[:12], ", ".join(after[:5])))
        for w in warnings:
            print("::warning file=%s::%s" % (path, w))
        for e in errors:
            print("::error file=%s::%s" % (path, e))
        print("%s %s (%d events, session %s)" % ("FAIL" if errors else "OK  ", path, len(b.get("events", [])), b.get("sessionId")))
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
