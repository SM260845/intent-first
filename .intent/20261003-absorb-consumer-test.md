---
id: 20261003-absorb-consumer-test
status: shipped
touches: [examples/consumer/, .github/workflows/consumer-demo.yml, README.md, CHANGELOG.md]
---
# Absorb the consumer test repo into examples/consumer/

## Want
`ao3575911/intent-first-consumer-test` lives in this repo as
`examples/consumer/`, with its history kept. Its pass/fail demo runs here in
CI: the action is run against the fixtures, a valid intent must pass and a
junk intent must fail, and the job asserts both outcomes. README links point
at the new location.

## Not
No change to the gate, its inputs or its rules. The consumer files under
`examples/consumer/` are fixtures, not intents for this repo.

## Done when
- The consumer fixtures are present
  check: `test -f examples/consumer/.intent/20261001-hello.md && test -f examples/consumer/.intent/hi.md`
- The fixture code runs
  check: `python3 examples/consumer/src/hello.py | grep -q hello`
- No README links to the old consumer repo remain
  check: `! grep -n "github.com/ao3575911/intent-first-consumer-test" README.md`
- The consumer-demo workflow passes: valid intent passes, junk intent fails
