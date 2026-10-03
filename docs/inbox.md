# Intent Inbox

For teams handing work to agents. Write the intent and let any coding agent or person build it. CI picks the winner.

You don't need the Inbox to use intent-first. The core gate and `git why` in the [README](../README.md) work on their own.

![Intent Inbox: replay of the real demo run, where claim #24 fails, claim #26 passes and is merged, and issue #25 is closed](inbox-demo.gif)

## How it works

1. Anyone proposes an intent by PR into `.intent/open/`. The `intent-intake` check fails until an owner, member or collaborator other than the PR author approves the PR's latest commit.
2. Once it merges, the inbox opens an issue labelled `intent-open` with the intent and how to claim it.
3. Claim PRs put `Claims: <id>` in the body, and intent-check runs that intent's `check:` lines on each one.
4. The first claim whose CI passes is squash-merged at the SHA that passed, and the other claims are closed with a comment. A sweep every 30 minutes retries passing claims that weren't merged. A claim that's behind the base branch gets one comment asking for an update.
5. The issue is closed with the `shipped` label. That closed issue is the record that the intent is done, so intent files never move or change. An intent can be claimed only while its issue is open: close the issue as not planned to retire it.

## Setup

The Inbox runs alongside the core [intent-check workflow](../README.md#quickstart). Add two workflows, and make `intent-intake` a required status check. Turn on "Require branches to be up to date" too; the inbox waits for a behind claim to be updated instead of merging it stale.

```yaml
# .github/workflows/intent-intake.yml
name: intent-intake
on:
  pull_request: {types: [opened, synchronize, reopened]}
  pull_request_review: {types: [submitted, dismissed]}
permissions: {contents: read, pull-requests: read}
jobs:
  intent-intake:
    runs-on: ubuntu-latest
    steps:
      - uses: ao3575911/intent-first/inbox@v1
        with: {mode: intake}
```

```yaml
# .github/workflows/intent-inbox.yml
name: intent-inbox
on:
  push: {branches: [main], paths: [".intent/open/**"]}
  workflow_run: {workflows: [intent-check], types: [completed]}   # the name of your intent-check workflow
  schedule: [{cron: "*/30 * * * *"}]                              # the sweep
  workflow_dispatch:
permissions: {}
jobs:
  open:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    permissions: {contents: read, issues: write}
    steps:
      - uses: actions/checkout@v5
        with: {fetch-depth: 0, persist-credentials: false}
      - uses: ao3575911/intent-first/inbox@v1
        with: {mode: open}
  claims:
    if: github.event_name != 'push' && (github.event_name != 'workflow_run' || (github.event.workflow_run.event == 'pull_request' && github.event.workflow_run.conclusion == 'success'))
    runs-on: ubuntu-latest
    permissions: {pull-requests: read, actions: read}
    outputs: {claims: "${{ steps.c.outputs.claims }}"}
    steps:
      - id: c
        uses: ao3575911/intent-first/inbox@v1
        with: {mode: claims, workflow: intent-check.yml}   # the file name of that workflow
  ship:
    needs: claims
    if: needs.claims.outputs.claims != '[]'
    runs-on: ubuntu-latest
    strategy: {fail-fast: false, matrix: {include: "${{ fromJSON(needs.claims.outputs.claims) }}"}}
    concurrency: {group: "intent-inbox-ship-${{ matrix.intent }}", cancel-in-progress: false}
    permissions: {contents: write, pull-requests: write, issues: write, actions: read}
    steps:
      - uses: ao3575911/intent-first/inbox@v1
        with: {mode: ship, run-id: "${{ matrix.run }}"}   # protect: "scripts/" keeps claims out of more paths
```

An intent without `check:` lines can't be claimed: its issue says so, and claim PRs fail. To assign each new issue to Copilot coding agent, set `assignees: copilot-swe-agent[bot]` on the `open` step. That needs a user token in `token:` and a Copilot plan that includes the coding agent.

## Inputs

`ao3575911/intent-first/inbox@v1` ([inbox/action.yml](../inbox/action.yml)):

<!-- generated from inbox/action.yml -->
| Input | Default | Description |
|---|---|---|
| `mode` | required | `intake` (on pull_request and pull_request_review), `open` (on push to the default branch), `claims` (on workflow_run, schedule or workflow_dispatch; outputs the passing claims) or `ship` (merges the claim whose run passed). |
| `token` | `${{ github.token }}` | Token for the GitHub API. |
| `assignees` | `""` | Optional comma-separated logins to assign each new intent issue to, e.g. copilot-swe-agent[bot]. Needs a user token. |
| `workflow` | `""` | For `claims` on a schedule. The file name of the workflow that runs intent-check on claim PRs, e.g. intent-check.yml. |
| `run-id` | `""` | For `ship`. The id of the CI run that passed. Defaults to the triggering workflow_run. |
| `protect` | `""` | For `ship`. Comma-separated paths a claim may never change, on top of .intent/ and .github/, e.g. action.yml,scripts/. |

Output: `claims`, from `claims` mode: a JSON list of `{intent, run}`, the earliest passing claim per intent.

## Security

- A PR that changes `.intent/open/` needs an approving review on its latest commit from an owner, member or collaborator other than the PR author. Bot approvals don't count, and a new commit needs a new approval.
- PRs from forks skip `check:` commands unless `run-checks-on-forks` is `"true"`. A fork claim whose checks were skipped fails, so the inbox never merges it.
- The inbox's `claims` and `ship` jobs run code from the default branch, never check out the PR, and merge only the SHA that passed. A claim merges only if every changed file is inside the intent's `touches:` and none is under `.intent/`, `.github/` or a `protect:` path. They read every page of a PR's files; a PR with more than 3000 files is never merged or approved. Claim PRs can't change `.intent/`.

## Tracing Inbox work

`git why` finds intents in `.intent/open/` and `.intent/shipped/`, and reads `Claims: <id>` like `Intent: <id>`, so `git why file:line` works on code that shipped through the Inbox.
