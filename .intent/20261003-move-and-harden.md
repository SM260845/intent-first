---
id: 20261003-move-and-harden
status: shipped
touches: [README.md, CHANGELOG.md, LICENSE, action.yml, scripts/intent_check.py, scripts/__pycache__/, .github/, .gitignore, ruff.toml]
---
# Move to ao3575911 and harden the gate

## Want
The repo now lives at `ao3575911/intent-first`, so every link, CODEOWNERS
entry and `uses:` line points there. The floating `v1` tag moves on each
release. CI runs on `main` as well as PRs, with ruff. `check:` commands from
fork PRs are skipped by default because they are PR-authored code.

## Not
No change to the intent rules themselves. Existing workflows keep working:
`run-checks` still defaults to `true` for same-repo PRs.

## Done when
- No references to the old owner remain outside `.intent/`
  check: `! grep -rn "SM260845" --exclude-dir=.git --exclude-dir=.intent .`
- Lint is clean (the selftest job runs `pipx run ruff check .`)
- Self-tests pass
  check: `python3 scripts/test_intent_check.py && python3 scripts/test_proof_check.py && python3 scripts/test_git_why.py`
- No compiled Python files are tracked
  check: `test -z "$(git ls-files '*.pyc')"`
