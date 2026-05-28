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

## Agent Branches

When using a sub-agent that should not see notes from other branches, create a dedicated branch memory first.

```bash
memoc branch sub-branch
```

When an agent should write while seeing notes from multiple branches, create a dedicated branch memory and expose all branch memories through `.memoc/branch`.

```bash
memoc branch agent --all
```
