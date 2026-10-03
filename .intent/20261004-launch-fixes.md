---
id: 20261004-launch-fixes
status: shipped
touches: [action.yml, bin/, scripts/, README.md, CONTRIBUTING.md, CHANGELOG.md, docs/]
---
# Launch fixes: skip the gate, trace Inbox work, lead with the core loop

## Want
The fixes from the launch review, except the Marketplace listing. The action
gets `exempt-authors`, `exempt-paths` and `skip-label`, and a skipped PR
passes with a notice. `git why` finds intents in `.intent/open/` and
`.intent/shipped/`, reads `Claims:` trailers, and `--init <slug>` writes
today's template. `touches:` accepts a YAML block list, headings match
regardless of case, and the `intent` output stays empty for an id that
doesn't exist. The README leads with the core loop and a GIF from a real
run, shows `git blame` vs `git why`, says when not to use it, and documents
skips, local runs, toolchain setup and draft vs shipped. The Inbox moves to
`docs/inbox.md`, and `docs/AGENTS-snippet.md` gives agents the rules. Stale
links and the proof notice are fixed.

## Not
No change to the Inbox's merge rules, the proof format or workflows. No
change to shipped intents. No new dependencies. A PR that changes `.intent/`
is never skipped.

## Done when
- Gate self-tests pass, including skips, block lists, headings and the output
  check: `python3 scripts/test_intent_check.py`
- git why self-tests pass, including .intent/shipped/, Claims: and --init
  check: `python3 scripts/test_git_why.py`
- Proof and Inbox self-tests still pass
  check: `python3 scripts/test_proof_check.py && python3 scripts/test_intent_inbox.py && python3 scripts/test_intent_inbox_api.py`
- Every gate input in action.yml is in the README inputs table
  check: `for i in $(awk '/^inputs:/{f=1;next} /^[a-z]/{f=0} f&&/^  [a-z-]+:/{sub(/:.*/,"");print $1}' action.yml); do grep -q "^| .$i. |" README.md || exit 1; done`
- The core-loop GIF exists and is under 2 MB, and the moved docs exist
  check: `test -f docs/core-loop.gif && [ "$(wc -c < docs/core-loop.gif)" -lt 2097152 ] && test -f docs/inbox.md && test -f docs/AGENTS-snippet.md`
- The rules anchor exists and CONTRIBUTING no longer lists closed #31
  check: `grep -q '^### Rules' README.md && ! grep -q 'issues/31' CONTRIBUTING.md`
- Ruff passes, and every README link resolves
