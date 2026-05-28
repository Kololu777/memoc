---
name: memoc-create
description: Initialize memoc for a new or unconfigured Git repository by creating the repository memory book under memory-books and local .memoc links. Use when asked to make memoc available, create .memoc, or create the memory-books area for a repository.
---

# Memoc Create

## Purpose

Use the `memoc` CLI to create a memory book for a repository under `memory-books` and create `.memoc/` in the working repository.

## Steps

1. Confirm the working directory is inside the target Git repository.
2. Run `git rev-parse --show-toplevel`, then run later `memoc` commands from the repository root.
3. Run `memoc init` to create the repository memory book and `share/` under `memory-books`.
4. Run `memoc branch` to create the current branch memory book plus `.memoc/share` and `.memoc/branch`.
5. Run `ls -la .memoc` and confirm `share` and `branch` are symlinks.

## Configuration

`memoc` uses `memory_books_root` from `~/.config/memoc/config.toml`. If it is not configured, `memoc init` creates the config file and stops; ask the user for the `memory-books` repository path.

Respect `MEMOC_CONFIG`, `memoc --config`, and `MEMOC_MEMORY_BOOKS_ROOT` when the user provides them.

## Safety

- Treat `.memoc/` as local state. Do not add it to Git.
- Do not invent the `memory-books` path.
- Do not overwrite existing files at `.memoc/share` or `.memoc/branch`.
