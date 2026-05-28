# memoc

`memoc` is a small CLI for keeping repository notes outside the working tree.

It creates a per-repository memory book under a separate `memory-books` directory
and exposes it from the current repository through local `.memoc/` symlinks.

```text
.memoc/share  -> repository-wide notes
.memoc/branch -> branch-specific notes
```

The intended setup is to manage `memory-books` as a private Git repository.
`memoc` then gives each source repository its own note area inside that private
repository.

## Requirements

- Python 3.12 or later
- Git
- ghq recommended
- Nix optional

`memoc` works best with repositories managed by `ghq`, but it also supports
worktrees outside `ghq`, such as `gwq` or `~/worktrees`.

## Install

### Nix

From this repository:

```bash
nix profile install .
```

You can also run it without installing:

```bash
nix run .# -- --help
nix run .#init
nix run .#branch
```

### Python

From this repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Configuration

Create a private `memory-books` repository wherever you want to store notes.
Then point `memoc` at it.

The default config file is:

```text
~/.config/memoc/config.toml
```

Example:

```toml
memory_books_root = "/home/alice/ghq/github.com/alice/memory-books"
```

You can override the root temporarily with an environment variable:

```bash
export MEMOC_MEMORY_BOOKS_ROOT=/home/alice/ghq/github.com/alice/memory-books
```

You can also use a different config file:

```bash
memoc --config /path/to/config.toml init
```

If the config file does not exist, `memoc init` creates a template and asks you
to set `memory_books_root`.

## Quick Start

In a Git repository:

```bash
memoc init
memoc branch
```

This creates the repository memory book and links it into the working tree:

```text
.memoc/share
.memoc/branch
```

`.memoc/` is local state. Add it to `.gitignore` in repositories where you use
`memoc`.

## Usage

### `memoc init`

Create the repository-wide memory book and `share/`.

```bash
memoc init
```

Example output path:

```text
/home/alice/ghq/github.com/alice/memory-books/github.com/org/repo
```

### `memoc branch`

Create a memory book for the current Git branch and point `.memoc/branch` at it.

```bash
memoc branch
```

If the current Git branch is `main`, this creates:

```text
memory-books/github.com/org/repo/branch/main
```

And links:

```text
.memoc/share  -> memory-books/github.com/org/repo/share
.memoc/branch -> memory-books/github.com/org/repo/branch/main
```

### `memoc branch <name>`

Create a memory book for a named branch without switching Git branches, then
point `.memoc/branch` at that named branch memory.

```bash
memoc branch feature/foo
```

This creates:

```text
memory-books/github.com/org/repo/branch/feature/foo
```

### `memoc branch --all`

Create a memory book for the current Git branch, then point `.memoc/branch` at
the parent directory containing all branch memories.

```bash
memoc branch --all
```

If the current Git branch is `agent`, this creates:

```text
memory-books/github.com/org/repo/branch/agent
```

And links:

```text
.memoc/branch -> memory-books/github.com/org/repo/branch
```

That makes all branch memories visible under `.memoc/branch/`.

### `memoc branch <name> --all`

Create a named branch memory, then expose all branch memories through
`.memoc/branch`.

```bash
memoc branch agent --all
```

This is useful for agents or review workflows that should create their own
branch memory while still reading notes from other branches.

## Path Resolution

`memoc` chooses the memory-book path in this order:

1. If the current repository is under a `ghq` root, use the path relative to
   that `ghq` root.
2. If the current repository is a worktree outside `ghq`, use the common
   worktree root when that root is under `ghq`.
3. If neither works, parse `origin` and use a path like
   `github.com/org/repo`.

For example, this source repository:

```text
/home/alice/ghq/github.com/org/repo
```

maps to:

```text
memory-books/github.com/org/repo
```

A `gwq` or `git worktree` checkout of the same repository should map to the
same memory book.

## Suggested Note Layout

`memoc` does not enforce note filenames or formats. A common pattern is:

```text
.memoc/share/project.md
.memoc/share/commands.md
.memoc/branch/session.md
.memoc/branch/todo.md
```

Use `.memoc/share/` for notes that should survive branch changes.
Use `.memoc/branch/` for notes about the current branch or task.

## Development

Run tests:

```bash
python -m unittest discover -s tests
```

Use the Nix development shell:

```bash
nix develop
```

Build and run with Nix:

```bash
nix run .# -- --help
```
