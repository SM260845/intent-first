---
id: 20260928-rate-limit-login-per-account
status: shipped
supersedes: 20260928-rate-limit-login
touches: [src/, tests/]
---
# Rate-limit failed logins per IP and per account

## Want
Keep max 5 failed logins per IP per minute. Also cap failures per account at
10 per minute, so one attacker spreading attempts across many IPs can't
brute-force a single account.

## Not
No CAPTCHA. No lockout for users who log in successfully: a success clears
both the IP's and the account's counters. No new dependencies.
No edits to `20260928-rate-limit-login.md`; it stays as the record of v1.

## Done when
- Per-IP behaviour from the superseded intent still holds
  check: `python3 -m unittest tests.test_ratelimit.BlockTest tests.test_ratelimit.WindowTest -v`
- The 11th failure for one account within 60s is refused, even from fresh IPs
  check: `python3 -m unittest tests.test_ratelimit.AccountTest -v`
