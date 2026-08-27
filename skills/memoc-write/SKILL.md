---
name: memoc-write
description: Read, create, and safely update repository memory notes through memoc's JSON CLI. Use for branch-scoped or shared memoc notes. Do not write note content through .memoc symlinks.
---

# Memoc Write

Use the `memoc` CLI for note content. Treat `.memoc/share`, `.memoc/branch`,
and `.memoc/branches` as compatibility links for humans, not as the agent's
read or write API.

## Prepare the context

Run commands from the source repository root.

1. Run `memoc context --json`.
2. If `manifest_exists` is false, run `memoc migrate --json`, then run
   `memoc context --json` again.
3. If the installed CLI does not recognize `context`, `migrate`, `list`,
   `read`, or `write`, stop and report that memoc must be updated. Do not fall
   back to editing `.memoc` paths directly.
4. On storage or permission failures, run `memoc doctor --json` and report its
   result.

## Choose the scope

Use `share` for information that should survive branch changes. Use `branch`
for information specific to the selected memory branch. A branch operation
uses the branch from `memoc context --json` unless the task explicitly needs
`--branch <name>`.

## Inspect notes

Use machine-readable output so paths and opaque versions are preserved exactly.

```bash
memoc list share --json
memoc list branch --json
memoc read share design/plan.md --json
memoc read branch todo.md --json
```

## Create a note

Pass the exact UTF-8 content on standard input and request JSON output.
Omitting `--expected-version` is create-only and must fail if the note already
exists.

```bash
memoc write share design/plan.md --json < prepared-note.md
```

Do not interpolate note content into a shell command. Use the execution tool's
standard-input facility or redirect a prepared file.

## Update a note

1. Read the note with `memoc read <scope> <path> --json`.
2. Preserve the returned `version` as an opaque string.
3. Edit the returned content.
4. Send the replacement content on standard input and pass the exact version:

```bash
memoc write share design/plan.md \
  --expected-version '<opaque-version>' --json < prepared-note.md
```

If the command returns `version_conflict`, re-read the note and reconcile the
new content before retrying. Never substitute the latest version merely to
force an overwrite. Ask the user when reconciliation is ambiguous.

## Provenance

For a new note, include a short header near the top:

```markdown
Created: YYYY-MM-DD
Author: Codex | Claude | <agent name>
Agent session: `<session id or unknown>`
Checkout: `<current git branch or checkout>`
```

For Codex, use `CODEX_THREAD_ID` when available. Preserve an existing
`Created` value. For meaningful edits, add or update `Updated: YYYY-MM-DD` and
a concise entry in the note's `## Changelog` section when that history is
useful.

## Agent branches

Use `memoc branch <name>` when an agent needs a dedicated branch memory. Add
`--all` only when the task requires visibility of other branch memories. These
commands may maintain compatibility symlinks; subsequent note operations must
still use `memoc list`, `memoc read`, and `memoc write`.
