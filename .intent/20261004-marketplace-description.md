---
id: 20261004-marketplace-description
status: open
touches: [action.yml]
---
# Shorten the action description for the Marketplace

## Want
`action.yml` description reads: "One intent per PR. Checks the .intent/ file (Want / Not / Done when) and runs its checks."

## Not
No change to inputs, outputs, branding, or behaviour. No other files change.

## Done when
- The description no longer mentions sealed agent session proofs
  check: `! grep '^description:' action.yml | grep -qi sealed`
- The description fits the Marketplace's 125-character limit
  check: `test $(grep '^description:' action.yml | sed 's/^description: //' | wc -c) -le 126`
