# memoc

`memoc` is a small CLI for keeping repository notes outside the working tree.

It creates a per-repository memory book under a separate `memory-books` directory
and exposes it from the current repository through local `.memoc/` symlinks.

```text
.memoc/share    -> repository-wide notes
.memoc/branch   -> selected branch notes
.memoc/branches -> all branch notes, created only when requested
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
nix run .#migrate -- --json
```

The Nix package contains both the CLI and the two Codex skills under
`share/memoc/skills`. The exported Home Manager module installs the executable
and those skills from the same immutable package output:

```nix
{
  imports = [ inputs.memoc.homeManagerModules.default ];
  programs.memoc.enable = true;
}
```

This creates one canonical `~/.codex/skills/memoc-create` and
`~/.codex/skills/memoc-write`. Remove independently installed copies such as
`~/.codex/skills/share/memoc-write`; Codex does not merge same-named skills.

### Python

From this repository:

```bash
uv sync
uv run memoc --version
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
.memoc/context.toml
```

`context.toml` is a regular local file that records the logical source
repository and selected memory branch. It contains no credentials or
machine-specific `memory_books_root` path.

```toml
schema_version = 1
repository = "github.com/org/repo"
source_branch = "main"
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

Create a memory book for the current Git branch, keep `.memoc/branch` pointing
at that current branch memory, and create `.memoc/branches` pointing at the
parent directory containing all branch memories.

```bash
memoc branch --all
```

If the current Git branch is `agent`, this creates:

```text
memory-books/github.com/org/repo/branch/agent
```

And links:

```text
.memoc/branch   -> memory-books/github.com/org/repo/branch/agent
.memoc/branches -> memory-books/github.com/org/repo/branch
```

That makes the selected branch writable through `.memoc/branch/` while all
branch memories are visible under `.memoc/branches/`.

### `memoc branch <name> --all`

Create a named branch memory, keep `.memoc/branch` pointing at that named branch
memory, and expose all branch memories through `.memoc/branches`.

```bash
memoc branch agent --all
```

This is useful for agents or review workflows that should create their own
branch memory while still reading notes from other branches.

### `memoc context`

Show the logical repository and selected memory branch. Use `--json` for a
machine-readable result.

```bash
memoc context --json
```

The selected branch is the branch passed to the most recent `memoc branch`
command. It can intentionally differ from the current Git branch.

### `memoc migrate`

Create `.memoc/context.toml` for a checkout initialized by an older memoc
version. Migration reads the legacy branch symlink itself but does not replace
or follow it into note storage.

```bash
memoc migrate --json
```

The command is idempotent. If the legacy branch link is unavailable, provide a
known branch explicitly:

```bash
memoc migrate --branch main --json
```

Use `memoc branch <name>` instead when intentionally changing a branch already
recorded in `context.toml`.

### `memoc list`

List notes in repository-wide or branch memory. An optional path prefix limits
the recursive listing.

```bash
memoc list share
memoc list share design --json
memoc list branch --branch feature/foo --json
```

When `--branch` is omitted for branch scope, memoc uses the selected branch
from `.memoc/context.toml`.

### `memoc read`

Read a UTF-8 note. The default output is the exact note content; JSON output
also includes its opaque version token and byte size.

```bash
memoc read share project.md
memoc read branch todo.md --json
```

### `memoc write`

Create a note from standard input with create-only semantics:

```bash
memoc write share project.md < project.md
```

Creating an existing note fails. To update a note, first obtain its version
with `memoc read --json`, then provide that version explicitly:

```bash
memoc write share project.md \
  --expected-version sha256:0123456789abcdef... < project.md
```

An update fails with `version_conflict` if the note changed after it was read.
There is no blind-overwrite mode. Local versions currently use SHA-256, but
callers should treat the version string as opaque so other storage backends can
use their own version format. On supported POSIX platforms, concurrent memoc
writers serialize the version check and atomic replacement with a note-level
lock. Editors writing the underlying file directly do not participate in that
lock.

### `memoc doctor`

Inspect the context manifest, configured local memory book, and `.memoc`
symlinks without modifying them.

```bash
memoc doctor
memoc doctor --json
```

The `context`, `list`, `read`, `write`, and `doctor` commands resolve the
configured `memory_books_root` directly and do not traverse `.memoc/share` or
`.memoc/branch`. They still require the memoc process itself to have filesystem
permission for `memory_books_root`. Give the CLI a narrow writable root or
command approval when possible; MCP or a remote backend is only needed when
that access cannot be granted.

## Python Storage API

The CLI note operations use a backend-neutral service boundary:

```python
from pathlib import Path

from memory_core import LocalFilesystemStore, MemoryService, NoteRef

service = MemoryService(LocalFilesystemStore(Path("/path/to/memory-books")))
ref = NoteRef(
    repository="github.com/org/repo",
    scope="share",
    path="project.md",
)
note = service.read_note(ref)
service.write_note(ref, "updated\n", expected_version=note.version)
```

`MemoryStore` defines `list`, `read`, and version-checked `write`. Future MCP
and GitHub backends can implement that protocol without changing the CLI-facing
note model.

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
Use `.memoc/branches/` only when you intentionally want to inspect notes from
other branches.

Those paths describe the human-compatible layout. Agents should use
`memoc list`, `memoc read`, and version-checked `memoc write` instead of editing
the symlink paths directly.

## Documentation

The current storage, context, CLI, consistency, and backend-extension contracts
are documented with Sphinx under `docs/`.

```bash
uv run --group docs sphinx-build -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` after the build. The specification is written
in Japanese and includes CLI and Python examples.

## Development

Run tests:

```bash
uv run python -m unittest discover -s tests
```

Use the Nix development shell:

```bash
nix develop
```

Build and run with Nix:

```bash
nix run .# -- --help
```
