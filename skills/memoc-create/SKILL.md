---
name: memoc-create
description: Initialize memoc for a new Git repository or migrate an existing symlink-only setup to a regular context manifest. Use when asked to configure memoc or create .memoc local state.
---

# Memoc Create

Initialize or migrate memoc through its CLI. Do not create memory-book paths or
`.memoc` links manually.

## Verify the CLI

Run commands from the source repository root. Confirm that
`memoc migrate --help` succeeds. If it does not, stop and report that the
installed memoc is too old; do not reproduce the setup with direct filesystem
operations.

## New repository setup

1. Confirm the target with `git rev-parse --show-toplevel`.
2. Run `memoc init`.
3. Run `memoc branch` or `memoc branch <name>` when the user selected a
   particular memory branch.
4. Run `memoc context --json` and require `manifest_exists` to be true.
5. Run `memoc doctor --json` and report any inaccessible local storage.

`memoc branch` creates `.memoc/context.toml` as a regular file and retains the
legacy `.memoc/share` and `.memoc/branch` symlinks for compatibility.

## Existing symlink-only setup

Run `memoc context --json`. If `manifest_exists` is false, run:

```bash
memoc migrate --json
```

Migration records the branch selected by the legacy `.memoc/branch` symlink
without replacing that link. If the legacy branch cannot be inferred, pass an
explicit branch only when it is known:

```bash
memoc migrate --branch main --json
```

Run `memoc context --json` afterward and require `manifest_exists` to be true.
Use `memoc branch <name>` instead of migration when intentionally changing an
already-recorded selected branch.

## Configuration

Memoc reads `memory_books_root` from `~/.config/memoc/config.toml`. An absent
config causes `memoc init` to create a template and stop; ask the user for the
actual private memory-books repository path rather than inventing one.

Respect `MEMOC_CONFIG`, `memoc --config`, and `MEMOC_MEMORY_BOOKS_ROOT` when the
user provides them. A global `--config` option goes before the subcommand.

## Safety

- Treat `.memoc` as uncommitted local state.
- Do not overwrite ordinary files at `.memoc/share`, `.memoc/branch`, or
  `.memoc/context.toml`.
- Use the `memoc-write` workflow for note content; do not write through the
  compatibility symlinks.
