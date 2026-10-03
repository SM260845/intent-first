# Agent instructions snippet

Copy the block below into `AGENTS.md`, `CLAUDE.md` or `.github/copilot-instructions.md` in a repo that uses intent-first. It tells a coding agent to write the intent before the code, so the instruction you gave it becomes a reviewed file that CI checks.

````markdown
## Intents (intent-first)

Every pull request in this repo needs exactly one intent file. CI fails without it.

Before you write code:

1. If the task names an existing draft intent, use it: put `Intent: <id>` on its own line in the PR description. Otherwise create `.intent/YYYYMMDD-slug.md` with today's date and a short lowercase slug. `git why --init <slug>` writes the template if it's installed.
2. Frontmatter: `id` equal to the file name without `.md`, `status: draft`, and `touches:` listing the folders or files you plan to change, e.g. `touches: [src/auth/, tests/auth/]`.
3. Write `## Want` (what the change does), `## Not` (what it must not do or change) and `## Done when` (one `- ` bullet per result).
4. Under each bullet that a command can verify, add an indented `check:` line with a command that exits 0 when it's done:

   ```markdown
   ## Done when
   - Login tests pass
     check: `npm test -- login`
   ```

While you work:

- Only change paths listed in `touches:`. If you need to change something else, add it to `touches:` and say why in the PR description.
- Never edit an intent with `status: shipped`, and never edit or delete files in `.intent/open/` or `.intent/shipped/`. To change a shipped decision, add a new intent with `supersedes: <old-id>`.
- One PR, one intent. Don't fold unrelated work into it.

Before you open the PR:

- Run every `check:` command yourself and make sure each one passes.
- If this PR finishes the work, set `status: shipped`. If more PRs will follow, leave it as `draft`.
````

The rules the gate enforces are in the [README](../README.md#rules).
