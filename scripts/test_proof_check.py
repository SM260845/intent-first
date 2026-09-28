#!/usr/bin/env python3
"""Self-test for proof_check.py."""
import base64
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from proof_check import GENESIS, canonical, event_hash, merkle_root, verify_bundle  # noqa: E402

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proof_check.py")
FIX = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "proof", "valid.json")
NAME = "20260928-rate-limit-login"
SHA256_WITH_NULL_AND_OCTET = bytes.fromhex("060960864801650304020105000420")


def intent(id_):
    return f"""---
id: {id_}
status: draft
touches: [src/]
---
# Title

## Want
Something.

## Not
Nothing else.

## Done when
- it works
"""


def make_bundle(intent_id, commit, session_id="test-session"):
    events = [
        {
            "sessionId": session_id,
            "id": "1",
            "type": "message",
            "ts": "2026-09-28T00:00:00Z",
            "payload": {
                "text": "Rate-limit logins é ✓",
                "numbers": [1e-7, 1e-6, 1e20, 1e21],
            },
        },
        {
            "sessionId": session_id,
            "id": "2",
            "type": "note",
            "ts": "2026-09-28T00:00:01Z",
            "payload": {"kind": "proof.link", "intent": intent_id, "commit": commit},
        },
    ]
    prev = GENESIS
    sealed = []
    for seq, event in enumerate(events):
        item = copy.deepcopy(event)
        seal = {"seq": seq, "prev": prev, "hash": event_hash(item, prev)}
        item["seal"] = seal
        sealed.append(item)
        prev = seal["hash"]
    hashes = [e["seal"]["hash"] for e in sealed]
    return {
        "v": 1,
        "intent": intent_id,
        "sessionId": session_id,
        "commit": commit,
        "createdAt": "2026-09-28T00:00:02Z",
        "events": sealed,
        "batches": [{
            "from": 0,
            "to": len(sealed) - 1,
            "root": merkle_root(hashes),
            "prevRoot": GENESIS,
            "ts": "2026-09-28T00:00:03Z",
        }],
    }


class Repo:
    def __init__(self):
        self.d = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("README.md", "x\n")
        self.commit("base")
        self.base = self.rev()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.d, check=True, capture_output=True, text=True).stdout.strip()

    def write(self, path, text):
        full = os.path.join(self.d, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def mv(self, src, dst):
        self.git("mv", src, dst)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def rev(self):
        return self.git("rev-parse", "HEAD")

    def check(self):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY")}
        r = subprocess.run([sys.executable, CHECK, "--base", self.base, "--head", self.rev()], cwd=self.d,
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr

    def add_feature(self, intent_id=NAME):
        self.write(f".intent/{intent_id}.md", intent(intent_id))
        self.write("src/a.py", "print(1)\n")
        self.commit("feature")
        return self.rev()

    def add_bundle(self, intent_id, linked_commit, path=None):
        self.write(path or f".proof/{intent_id}.json", json.dumps(make_bundle(intent_id, linked_commit), indent=2) + "\n")
        self.commit("proof")


class ProofCheck(unittest.TestCase):
    def setUp(self):
        with open(FIX, encoding="utf-8") as f:
            self.b = json.load(f)

    def test_valid_bundle_passes(self):
        errors, warnings = verify_bundle(self.b, NAME)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_edited_event_fails(self):
        b = copy.deepcopy(self.b)
        b["events"][0]["payload"]["text"] = "No rate limit"
        self.assertTrue(any("modified after sealing" in e for e in verify_bundle(b, NAME)[0]))

    def test_borrowed_proof_fails(self):
        b = copy.deepcopy(self.b)
        b["intent"] = "20260929-other-feature"
        errors = verify_bundle(b, "20260929-other-feature")[0]
        self.assertTrue(any("proof.link" in e for e in errors))

    def test_swapped_commit_fails(self):
        b = copy.deepcopy(self.b)
        b["commit"] = "f" * 40
        self.assertTrue(any("proof.link" in e for e in verify_bundle(b, NAME)[0]))

    def test_dropped_event_fails(self):
        b = copy.deepcopy(self.b)
        del b["events"][1]
        self.assertTrue(verify_bundle(b, NAME)[0])

    def test_wrong_filename_fails(self):
        self.assertTrue(any("file name" in e for e in verify_bundle(self.b, "20260101-x")[0]))

    def test_canonical_matches_json_stringify_number_edges(self):
        self.assertEqual(
            canonical([1e-7, 1e-6, 1e20, 1e21, -0.0, float("nan"), float("inf"), -float("inf")]),
            "[1e-7,0.000001,100000000000000000000,1e+21,0,null,null,null]",
        )
        self.assertEqual(
            canonical({
                "\uE000": "bmp",
                "\U0001F600": "astral",
                "\ud800": "surrogate",
                "text": "\ud800 😀",
            }),
            '{"text":"\\ud800 😀","\\ud800":"surrogate","😀":"astral","":"bmp"}',
        )

    def test_forged_timestamp_fails(self):
        b = copy.deepcopy(self.b)
        root = bytes.fromhex(b["batches"][0]["root"])
        forged = b"\x30\x03\x02\x01\x00" + SHA256_WITH_NULL_AND_OCTET + root
        b["batches"][0]["tsa"]["tsr"] = base64.b64encode(forged).decode()
        self.assertTrue(any("timestamp" in e.lower() for e in verify_bundle(b, NAME)[0]))


class ProofCheckCli(unittest.TestCase):
    def test_valid_bundle_passes_pr_checks(self):
        r = Repo()
        linked = r.add_feature()
        r.add_bundle(NAME, linked)
        code, out = r.check()
        self.assertEqual(code, 0, out)
        self.assertIn(f"OK   .proof/{NAME}.json", out)

    def test_missing_intent_fails(self):
        r = Repo()
        r.write("src/a.py", "print(1)\n")
        r.commit("code")
        linked = r.rev()
        r.add_bundle(NAME, linked)
        code, out = r.check()
        self.assertEqual(code, 1, out)
        self.assertIn(f"no intent .intent/{NAME}.md", out)

    def test_linked_commit_must_be_in_pr(self):
        r = Repo()
        outside = r.rev()
        r.add_feature()
        r.add_bundle(NAME, outside)
        code, out = r.check()
        self.assertEqual(code, 1, out)
        self.assertIn("is not part of this PR", out)

    def test_code_change_after_linked_commit_fails(self):
        r = Repo()
        linked = r.add_feature()
        r.write("src/b.py", "print(2)\n")
        r.commit("late code")
        r.add_bundle(NAME, linked)
        code, out = r.check()
        self.assertEqual(code, 1, out)
        self.assertIn("code changed after the session's commit", out)
        self.assertIn("src/b.py", out)

    def test_renamed_bundle_is_still_checked(self):
        r = Repo()
        linked = r.add_feature()
        r.add_bundle(NAME, linked)
        r.mv(f".proof/{NAME}.json", ".proof/renamed.json")
        r.commit("rename proof")
        code, out = r.check()
        self.assertEqual(code, 1, out)
        self.assertIn(".proof/renamed.json", out)
        self.assertIn("file name", out)


if __name__ == "__main__":
    unittest.main()
