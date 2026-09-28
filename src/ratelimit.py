"""Login rate limiter.

Intent: 20260928-rate-limit-login-per-account
(supersedes 20260928-rate-limit-login)
"""
import time
from collections import defaultdict


class LoginRateLimiter:
    def __init__(self, max_failures=5, window_seconds=60, clock=time.monotonic,
                 max_account_failures=10):
        self.max_failures = max_failures
        self.max_account_failures = max_account_failures
        self.window = window_seconds
        self.clock = clock
        self._failures = defaultdict(list)
        self._account_failures = defaultdict(list)

    def _prune(self, store, key):
        cutoff = self.clock() - self.window
        store[key] = [t for t in store[key] if t > cutoff]
        return store[key]

    def allowed(self, ip, account=None):
        if len(self._prune(self._failures, ip)) >= self.max_failures:
            return False
        if account is not None:
            if len(self._prune(self._account_failures, account)) >= self.max_account_failures:
                return False
        return True

    def record_failure(self, ip, account=None):
        now = self.clock()
        self._prune(self._failures, ip).append(now)
        if account is not None:
            self._prune(self._account_failures, account).append(now)

    def record_success(self, ip, account=None):
        self._failures.pop(ip, None)
        if account is not None:
            self._account_failures.pop(account, None)
