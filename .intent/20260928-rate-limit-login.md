---
id: 20260928-rate-limit-login
status: shipped
touches: [src/, tests/]
---
# Rate-limit failed logins

## Want
Max 10 failed logins per IP per minute. The 6th attempt inside the window is refused.

## Not
No CAPTCHA. No lockout for users who log in successfully: a success clears the IP's counter.
No new dependencies.

## Done when
- The 6th failed login from one IP within 60s is refused, and other IPs are unaffected
  check: `python3 -m unittest discover -s tests -v`
- Failures older than 60s stop counting
  check: `python3 -m unittest tests.test_ratelimit.WindowTest -v`
