#!/usr/bin/env python3
"""proof-check: verify proof bundles in a proof-carrying PR.

A proof bundle (.proof/<intent-id>.json) is written by
`agent-session-recorder bundle <session> --intent <id>`. It holds the sealed
agent session, its Merkle batches (optionally RFC 3161 timestamped), and a
`proof.link` event naming the intent and the commit the session produced.

This is an independent, stdlib-only Python re-implementation of the recorder's
`verify`, with OpenSSL used for RFC 3161 signature checks.

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
import math
import os
import ssl
import subprocess
import sys
import tempfile
from decimal import Decimal

GENESIS = "0" * 64
PINNED_TSA_ROOTS = ["""-----BEGIN CERTIFICATE-----
MIIH/zCCBeegAwIBAgIJAMHphhYNqOmAMA0GCSqGSIb3DQEBDQUAMIGVMREwDwYD
VQQKEwhGcmVlIFRTQTEQMA4GA1UECxMHUm9vdCBDQTEYMBYGA1UEAxMPd3d3LmZy
ZWV0c2Eub3JnMSIwIAYJKoZIhvcNAQkBFhNidXNpbGV6YXNAZ21haWwuY29tMRIw
EAYDVQQHEwlXdWVyemJ1cmcxDzANBgNVBAgTBkJheWVybjELMAkGA1UEBhMCREUw
HhcNMTYwMzEzMDE1MjEzWhcNNDEwMzA3MDE1MjEzWjCBlTERMA8GA1UEChMIRnJl
ZSBUU0ExEDAOBgNVBAsTB1Jvb3QgQ0ExGDAWBgNVBAMTD3d3dy5mcmVldHNhLm9y
ZzEiMCAGCSqGSIb3DQEJARYTYnVzaWxlemFzQGdtYWlsLmNvbTESMBAGA1UEBxMJ
V3VlcnpidXJnMQ8wDQYDVQQIEwZCYXllcm4xCzAJBgNVBAYTAkRFMIICIjANBgkq
hkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAtgKODjAy8REQ2WTNqUudAnjhlCrpE6ql
mQfNppeTmVvZrH4zutn+NwTaHAGpjSGv4/WRpZ1wZ3BRZ5mPUBZyLgq0YrIfQ5Fx
0s/MRZPzc1r3lKWrMR9sAQx4mN4z11xFEO529L0dFJjPF9MD8Gpd2feWzGyptlel
b+PqT+++fOa2oY0+NaMM7l/xcNHPOaMz0/2olk0i22hbKeVhvokPCqhFhzsuhKsm
q4Of/o+t6dI7sx5h0nPMm4gGSRhfq+z6BTRgCrqQG2FOLoVFgt6iIm/BnNffUr7V
DYd3zZmIwFOj/H3DKHoGik/xK3E82YA2ZulVOFRW/zj4ApjPa5OFbpIkd0pmzxzd
EcL479hSA9dFiyVmSxPtY5ze1P+BE9bMU1PScpRzw8MHFXxyKqW13Qv7LWw4sbk3
SciB7GACbQiVGzgkvXG6y85HOuvWNvC5GLSiyP9GlPB0V68tbxz4JVTRdw/Xn/XT
FNzRBM3cq8lBOAVt/PAX5+uFcv1S9wFE8YjaBfWCP1jdBil+c4e+0tdywT2oJmYB
BF/kEt1wmGwMmHunNEuQNzh1FtJY54hbUfiWi38mASE7xMtMhfj/C4SvapiDN837
gYaPfs8x3KZxbX7C3YAsFnJinlwAUss1fdKar8Q/YVs7H/nU4c4Ixxxz4f67fcVq
M2ITKentbCMCAwEAAaOCAk4wggJKMAwGA1UdEwQFMAMBAf8wDgYDVR0PAQH/BAQD
AgHGMB0GA1UdDgQWBBT6VQ2MNGZRQ0z357OnbJWveuaklzCBygYDVR0jBIHCMIG/
gBT6VQ2MNGZRQ0z357OnbJWveuakl6GBm6SBmDCBlTERMA8GA1UEChMIRnJlZSBU
U0ExEDAOBgNVBAsTB1Jvb3QgQ0ExGDAWBgNVBAMTD3d3dy5mcmVldHNhLm9yZzEi
MCAGCSqGSIb3DQEJARYTYnVzaWxlemFzQGdtYWlsLmNvbTESMBAGA1UEBxMJV3Vl
cnpidXJnMQ8wDQYDVQQIEwZCYXllcm4xCzAJBgNVBAYTAkRFggkAwemGFg2o6YAw
MwYDVR0fBCwwKjAooCagJIYiaHR0cDovL3d3dy5mcmVldHNhLm9yZy9yb290X2Nh
LmNybDCBzwYDVR0gBIHHMIHEMIHBBgorBgEEAYHyJAEBMIGyMDMGCCsGAQUFBwIB
FidodHRwOi8vd3d3LmZyZWV0c2Eub3JnL2ZyZWV0c2FfY3BzLmh0bWwwMgYIKwYB
BQUHAgEWJmh0dHA6Ly93d3cuZnJlZXRzYS5vcmcvZnJlZXRzYV9jcHMucGRmMEcG
CCsGAQUFBwICMDsaOUZyZWVUU0EgdHJ1c3RlZCB0aW1lc3RhbXBpbmcgU29mdHdh
cmUgYXMgYSBTZXJ2aWNlIChTYWFTKTA3BggrBgEFBQcBAQQrMCkwJwYIKwYBBQUH
MAGGG2h0dHA6Ly93d3cuZnJlZXRzYS5vcmc6MjU2MDANBgkqhkiG9w0BAQ0FAAOC
AgEAaK9+v5OFYu9M6ztYC+L69sw1omdyli89lZAfpWMMh9CRmJhM6KBqM/ipwoLt
nxyxGsbCPhcQjuTvzm+ylN6VwTMmIlVyVSLKYZcdSjt/eCUN+41K7sD7GVmxZBAF
ILnBDmTGJmLkrU0KuuIpj8lI/E6Z6NnmuP2+RAQSHsfBQi6sssnXMo4HOW5gtPO7
gDrUpVXID++1P4XndkoKn7Svw5n0zS9fv1hxBcYIHPPQUze2u30bAQt0n0iIyRLz
aWuhtpAtd7ffwEbASgzB7E+NGF4tpV37e8KiA2xiGSRqT5ndu28fgpOY87gD3ArZ
DctZvvTCfHdAS5kEO3gnGGeZEVLDmfEsv8TGJa3AljVa5E40IQDsUXpQLi8G+UC4
1DWZu8EVT4rnYaCw1VX7ShOR1PNCCvjb8S8tfdudd9zhU3gEB0rxdeTy1tVbNLXW
99y90xcwr1ZIDUwM/xQ/noO8FRhm0LoPC73Ef+J4ZBdrvWwauF3zJe33d4ibxEcb
8/pz5WzFkeixYM2nsHhqHsBKw7JPouKNXRnl5IAE1eFmqDyC7G/VT7OF669xM6hb
Ut5G21JE4cNK6NNucS+fzg1JPX0+3VhsYZjj7D5uljRvQXrJ8iHgr/M6j2oLHvTA
I2MLdq2qjZFDOCXsxBxJpbmLGBx9ow6ZerlUxzws2AWv2pk=
-----END CERTIFICATE-----
"""]


def js_number(v):
    """Match JavaScript's JSON.stringify formatting for finite numbers."""
    if isinstance(v, int):
        return str(v)
    if not math.isfinite(v):
        return "null"
    if v == 0:
        return str(int(v))
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e21:
        return str(int(v))
    s = repr(v)
    if 1e-6 <= abs(v) < 1e21:
        s = format(Decimal(s), "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"
    mantissa, exponent = s.lower().split("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent = int(exponent)
    return mantissa + "e" + ("+" if exponent > 0 else "") + str(exponent)


def canonical(v):
    """Match the recorder's canonical JSON (sorted keys, no spaces, JS number format)."""
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return js_number(v)
    if isinstance(v, str):
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


def trusted_ca_args(tmp):
    cafile = os.path.join(tmp, "trusted-tsa.pem")
    paths = ssl.get_default_verify_paths()
    with open(cafile, "w", encoding="ascii") as f:
        if paths.cafile and os.path.exists(paths.cafile):
            with open(paths.cafile, encoding="ascii") as src:
                f.write(src.read())
            if f.tell():
                f.write("\n")
        for pem in PINNED_TSA_ROOTS:
            f.write(pem)
            if not pem.endswith("\n"):
                f.write("\n")
    args = ["-CAfile", cafile]
    if paths.capath and os.path.exists(paths.capath):
        args += ["-CApath", paths.capath]
    return args

def check_tsr(tsr, root):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tsr_path = os.path.join(tmp, "proof.tsr")
            with open(tsr_path, "wb") as f:
                f.write(tsr)
            r = subprocess.run(
                ["openssl", "ts", "-verify", "-in", tsr_path, "-digest", root, *trusted_ca_args(tmp)],
                capture_output=True,
                text=True,
            )
    except FileNotFoundError:
        return "OpenSSL is required to verify RFC 3161 timestamps"
    if r.returncode == 0:
        return None
    detail = (r.stderr or r.stdout).strip().splitlines()
    return "timestamp verification failed%s" % (": " + detail[-1] if detail else "")


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
    changed = [p for p in git("diff", "--name-only", "--diff-filter=AM", "--no-renames", a.base, a.head).splitlines()
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
