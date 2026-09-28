#!/usr/bin/env python3
"""Fixtures for proof_check: valid, edited, borrowed, dropped. Bundle written by agent-session-recorder."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from proof_check import verify_bundle  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "proof", "valid.json")
NAME = "20260928-rate-limit-login"


class ProofCheck(unittest.TestCase):
    def setUp(self):
        with open(FIX, encoding="utf-8") as f:
            self.b = json.load(f)

    def test_valid_bundle_passes(self):
        errors, warnings = verify_bundle(self.b, NAME)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])  # fixture carries a real freetsa.org timestamp

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


if __name__ == "__main__":
    unittest.main()
