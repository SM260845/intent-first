"""Login rate limiter. Intent: 20260928-rate-limit-login"""
import time
from collections import defaultdict


class LoginRateLimiter:
    def __init__(self, max_failures=5, window_seconds=60, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self.clock = clock
        self._failures = defaultdict(list)

    def allowed(self, ip):
        return len(self._failures[ip]) < self.max_failures

    def record_failure(self, ip):
        self._failures[ip].append(self.clock())

    def record_success(self, ip):
        self._failures.pop(ip, None)
