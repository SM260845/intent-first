---
id: 20261003-inbox-demo
status: draft
touches: [examples/inbox-demo/]
---
# Inbox demo: greet from the intent inbox

## Want
`examples/inbox-demo/greet.sh` prints exactly `hello from the intent inbox`.

## Not
No other files change.

## Done when
- The script prints the line
  check: `sh examples/inbox-demo/greet.sh | grep -qx 'hello from the intent inbox'`
