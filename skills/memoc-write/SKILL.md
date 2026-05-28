---
name: memoc-write
description: Guide where to write notes under memoc's .memoc directory. Write matters scoped to the current branch under .memoc/branch/ and matters that should be shared across branches under .memoc/share/. Leave note format, content, filenames, and granularity to the user or agent.
---

# Memoc Write

## Purpose

Guide notes into `.memoc`. The user or agent decides the content, format, filenames, and level of detail.

## Destinations

Write matters scoped to the current branch under `.memoc/branch/`.

Write matters that should be shared across branches under `.memoc/share/`.

If `.memoc/` does not exist, use `memoc-create` first.

## Provenance Header

For new memoc notes, include a short provenance header near the top:

```markdown
Created: YYYY-MM-DD
Author: Codex | Claude | <agent name>
Agent session: `<session id or unknown>`
Checkout: `<current git branch or checkout>`
```

For Codex, use `CODEX_THREAD_ID` as the session id when available.

For Claude Code, use the `session_id` from hook/statusline JSON when available.
If it is not available, write `unknown`.

When updating an existing note, preserve its original `Created` value. If
tracking the edit is useful, add or update the `Updated: YYYY-MM-DD` line near
the same header. Do not require `Updated` for every small edit.

For meaningful updates, add or update a `## Changelog` section in the note. Use it
as a short changelog for that Markdown file, not as a full conversation log.
Keep entries concise:

```markdown
## Changelog

- YYYY-MM-DD: <summary of what changed>
```

## Agent Branches

When using a sub-agent that should not see notes from other branches, create a dedicated branch memory first.

```bash
memoc branch sub-branch
```

When an agent should write while seeing notes from multiple branches, create a dedicated branch memory and expose all branch memories through `.memoc/branches`.

```bash
memoc branch agent --all
```
