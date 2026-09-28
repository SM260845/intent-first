import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ratelimit import LoginRateLimiter  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class BlockTest(unittest.TestCase):
    def test_sixth_failure_in_window_is_refused(self):
        rl = LoginRateLimiter(clock=FakeClock())
        for _ in range(5):
            self.assertTrue(rl.allowed("1.2.3.4"))
            rl.record_failure("1.2.3.4")
        self.assertFalse(rl.allowed("1.2.3.4"))

    def test_other_ips_unaffected(self):
        rl = LoginRateLimiter(clock=FakeClock())
        for _ in range(5):
            rl.record_failure("1.2.3.4")
        self.assertTrue(rl.allowed("5.6.7.8"))

    def test_success_clears_counter(self):
        rl = LoginRateLimiter(clock=FakeClock())
        for _ in range(4):
            rl.record_failure("1.2.3.4")
        rl.record_success("1.2.3.4")
        for _ in range(4):
            rl.record_failure("1.2.3.4")
        self.assertTrue(rl.allowed("1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
