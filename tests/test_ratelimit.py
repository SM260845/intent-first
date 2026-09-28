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


class WindowTest(unittest.TestCase):
    def test_failures_older_than_window_stop_counting(self):
        clock = FakeClock()
        rl = LoginRateLimiter(clock=clock)
        for _ in range(5):
            rl.record_failure("1.2.3.4")
        self.assertFalse(rl.allowed("1.2.3.4"))
        clock.t = 60.5
        self.assertTrue(rl.allowed("1.2.3.4"))

    def test_failures_inside_window_still_count(self):
        clock = FakeClock()
        rl = LoginRateLimiter(clock=clock)
        for i in range(5):
            clock.t = i * 10.0
            rl.record_failure("1.2.3.4")
        clock.t = 59.0
        self.assertFalse(rl.allowed("1.2.3.4"))


class AccountTest(unittest.TestCase):
    def test_eleventh_account_failure_refused_from_fresh_ip(self):
        rl = LoginRateLimiter(clock=FakeClock())
        for i in range(10):
            ip = f"10.0.0.{i}"
            self.assertTrue(rl.allowed(ip, "alice"))
            rl.record_failure(ip, "alice")
        self.assertFalse(rl.allowed("10.0.0.99", "alice"))
        self.assertTrue(rl.allowed("10.0.0.99", "bob"))

    def test_account_window_expires(self):
        clock = FakeClock()
        rl = LoginRateLimiter(clock=clock)
        for i in range(10):
            rl.record_failure(f"10.0.0.{i}", "alice")
        clock.t = 61.0
        self.assertTrue(rl.allowed("10.0.0.99", "alice"))

    def test_success_clears_account(self):
        rl = LoginRateLimiter(clock=FakeClock())
        for i in range(9):
            rl.record_failure(f"10.0.0.{i}", "alice")
        rl.record_success("10.0.0.50", "alice")
        rl.record_failure("10.0.0.51", "alice")
        self.assertTrue(rl.allowed("10.0.0.52", "alice"))


if __name__ == "__main__":
    unittest.main()
