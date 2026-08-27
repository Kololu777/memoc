from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from memory_core import __version__
from memory_core.config import ConfigError, load_config
from memory_core.context import (
    ContextError,
    MemoryContext,
    get_context_path,
    load_context,
    write_context,
)
from memory_core.service import MemoryService
from memory_core.store import (
    InvalidNoteReferenceError,
    LocalFilesystemStore,
    MemoryStoreError,
    NoteRef,
    NoteScope,
    NoteSummary,
    VersionConflictError,
    validate_logical_path,
)


class MemocError(RuntimeError):
    """Raised when a memoc command cannot complete."""


@dataclass(frozen=True)
class ResolvedMemoryContext:
    repo_root: Path
    memory_books_root: Path
    repository: str
    source_branch: str
    manifest_exists: bool

    @property
    def repo_memory_book_path(self) -> Path:
        return self.memory_books_root.joinpath(*self.repository.split("/"))


@dataclass(frozen=True)
class ContextMigrationResult:
    context: ResolvedMemoryContext
    migrated: bool
    source_branch_origin: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memoc")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config.toml. Defaults to ~/.config/memoc/config.toml.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create a memory-book directory for the current ghq-managed repository.",
    )
    init_parser.set_defaults(func=cmd_init)

    branch_parser = subparsers.add_parser(
        "branch",
        help="Create a memory-book directory for the current Git branch.",
    )
    branch_parser.add_argument(
        "branch_name",
        nargs="?",
        help="Branch name. Defaults to the current Git branch.",
    )
    branch_parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Create .memoc/branches pointing to the directory containing all branch "
            "memory books."
        ),
    )
    branch_parser.set_defaults(func=cmd_branch)

    context_parser = subparsers.add_parser(
        "context",
        help="Show the logical repository and selected branch memory.",
    )
    context_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    context_parser.set_defaults(func=cmd_context)

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Create a regular context manifest for an existing memoc setup.",
    )
    migrate_parser.add_argument(
        "--branch",
        help=(
            "Selected memory branch to record when no context manifest exists. "
            "Defaults to the legacy branch symlink or current Git branch."
        ),
    )
    add_json_argument(migrate_parser)
    migrate_parser.set_defaults(func=cmd_migrate)

    list_parser = subparsers.add_parser(
        "list",
        help="List notes without following local .memoc symlinks.",
    )
    add_note_scope_argument(list_parser)
    list_parser.add_argument(
        "prefix",
        nargs="?",
        default="",
        help="Optional note path prefix to list recursively.",
    )
    add_note_branch_argument(list_parser)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=cmd_list)

    read_parser = subparsers.add_parser(
        "read",
        help="Read a UTF-8 note without following local .memoc symlinks.",
    )
    add_note_scope_argument(read_parser)
    read_parser.add_argument("path", help="Note path relative to the selected scope.")
    add_note_branch_argument(read_parser)
    add_json_argument(read_parser)
    read_parser.set_defaults(func=cmd_read)

    write_parser = subparsers.add_parser(
        "write",
        help="Create or version-check and replace a UTF-8 note from stdin.",
    )
    add_note_scope_argument(write_parser)
    write_parser.add_argument("path", help="Note path relative to the selected scope.")
    add_note_branch_argument(write_parser)
    write_parser.add_argument(
        "--expected-version",
        help=(
            "Replace an existing note only when its version matches. Omit this "
            "option to create a new note and fail if it already exists."
        ),
    )
    add_json_argument(write_parser)
    write_parser.set_defaults(func=cmd_write)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Inspect memoc context, symlinks, and local storage access.",
    )
    add_json_argument(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    return parser


def add_note_scope_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "scope",
        choices=[scope.value for scope in NoteScope],
        help="Use repository-wide share notes or selected branch notes.",
    )


def add_note_branch_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--branch",
        help="Source branch memory. Defaults to the selected branch from context.",
    )


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )


def cmd_init(args: argparse.Namespace) -> int:
    target_path = init_memory_book(Path.cwd(), args.config)
    print(target_path)
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    target_path = init_branch_memory_book(
        Path.cwd(), args.config, args.branch_name, expose_all_branches=args.all
    )
    print(target_path)
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    context = resolve_memory_context(Path.cwd(), args.config)
    payload = context_payload(context)
    if args.json:
        print_json(payload)
    else:
        print(f"repository: {context.repository}")
        print(f"source_branch: {context.source_branch}")
        print("backend: filesystem")
        print(f"manifest: {get_context_path(context.repo_root)}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    result = migrate_context(Path.cwd(), args.config, branch_name=args.branch)
    payload = {
        **context_payload(result.context),
        "migrated": result.migrated,
        "source_branch_origin": result.source_branch_origin,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"migrated: {str(result.migrated).lower()}")
        print(f"repository: {result.context.repository}")
        print(f"source_branch: {result.context.source_branch}")
        print(f"source_branch_origin: {result.source_branch_origin}")
        print(f"manifest: {get_context_path(result.context.repo_root)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    context, service = resolve_local_service(Path.cwd(), args.config)
    scope = NoteScope(args.scope)
    source_branch = resolve_scope_branch(scope, args.branch, context)
    summaries = service.list_notes(
        repository=context.repository,
        scope=scope,
        source_branch=source_branch,
        prefix=args.prefix,
    )
    if args.json:
        print_json(
            {
                "repository": context.repository,
                "scope": scope.value,
                "source_branch": source_branch,
                "prefix": args.prefix,
                "notes": [note_summary_payload(summary) for summary in summaries],
            }
        )
    else:
        for summary in summaries:
            print(summary.ref.path)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    context, service = resolve_local_service(Path.cwd(), args.config)
    scope = NoteScope(args.scope)
    source_branch = resolve_scope_branch(scope, args.branch, context)
    ref = NoteRef(
        repository=context.repository,
        scope=scope,
        source_branch=source_branch,
        path=args.path,
    )
    note = service.read_note(ref)
    if args.json:
        print_json(
            {
                "repository": note.ref.repository,
                "scope": note.ref.scope.value,
                "source_branch": note.ref.source_branch,
                "path": note.ref.path,
                "content": note.content,
                "version": note.version,
                "size": note.size,
            }
        )
    else:
        sys.stdout.write(note.content)
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    context, service = resolve_local_service(Path.cwd(), args.config)
    scope = NoteScope(args.scope)
    source_branch = resolve_scope_branch(scope, args.branch, context)
    ref = NoteRef(
        repository=context.repository,
        scope=scope,
        source_branch=source_branch,
        path=args.path,
    )
    content = sys.stdin.read()
    result = service.write_note(
        ref,
        content,
        expected_version=args.expected_version,
    )
    if args.json:
        print_json(
            {
                "repository": result.ref.repository,
                "scope": result.ref.scope.value,
                "source_branch": result.ref.source_branch,
                "path": result.ref.path,
                "created": result.created,
                "version": result.version,
            }
        )
    else:
        action = "created" if result.created else "updated"
        print(f"{action} {result.ref.path} {result.version}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    context = resolve_memory_context(Path.cwd(), args.config)
    repo_memory_book_path = context.repo_memory_book_path
    share_path = repo_memory_book_path / "share"
    branch_path = (
        repo_memory_book_path / "branch" / Path(*context.source_branch.split("/"))
    )
    memory_book_status = path_access_payload(repo_memory_book_path)
    share_status = path_access_payload(share_path)
    branch_status = path_access_payload(branch_path)
    links_status = {
        "share": symlink_payload(context.repo_root / ".memoc" / "share"),
        "branch": symlink_payload(context.repo_root / ".memoc" / "branch"),
        "branches": symlink_payload(context.repo_root / ".memoc" / "branches"),
    }
    payload = {
        **context_payload(context),
        "memory_book": memory_book_status,
        "share": share_status,
        "source_branch_memory": branch_status,
        "links": links_status,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"repository: {context.repository}")
        print(f"source_branch: {context.source_branch}")
        print(f"manifest_exists: {str(context.manifest_exists).lower()}")
        print(
            "memory_book: "
            f"exists={str(memory_book_status['exists']).lower()} "
            f"readable={str(memory_book_status['readable']).lower()} "
            f"writable={str(memory_book_status['writable']).lower()}"
        )
        for name, link in links_status.items():
            print(
                f"{name}_link: symlink={str(link['is_symlink']).lower()} "
                f"target_exists={str(link['target_exists']).lower()}"
            )
    return 0


def init_memory_book(cwd: Path, config_path: Path | None = None) -> Path:
    target_path = resolve_repo_memory_book_path(cwd, config_path)
    target_path.mkdir(parents=True, exist_ok=True)
    (target_path / "share").mkdir(parents=True, exist_ok=True)
    return target_path


def init_branch_memory_book(
    cwd: Path,
    config_path: Path | None = None,
    branch_name: str | None = None,
    *,
    expose_all_branches: bool = False,
) -> Path:
    repo_root = find_git_root(cwd)
    repo_memory_book_path = init_memory_book(repo_root, config_path)
    branch_root_path = repo_memory_book_path / "branch"
    selected_branch_name = branch_name or find_current_branch(repo_root)
    branch_path = get_branch_path(selected_branch_name)
    target_path = branch_root_path / branch_path
    target_path.mkdir(parents=True, exist_ok=True)

    all_branches_path = branch_root_path if expose_all_branches else None
    create_local_memoc_links(
        repo_root,
        repo_memory_book_path,
        target_path,
        all_branches_path=all_branches_path,
    )
    config = load_config(config_path)
    try:
        repository = repo_memory_book_path.relative_to(
            config.memory_books_root
        ).as_posix()
    except ValueError as exc:
        raise MemocError(
            "resolved memory book is outside memory_books_root: "
            f"{repo_memory_book_path}"
        ) from exc
    write_context(
        repo_root,
        MemoryContext(
            repository=repository,
            source_branch=selected_branch_name,
        ),
    )
    return target_path


def resolve_memory_context(
    cwd: Path,
    config_path: Path | None = None,
) -> ResolvedMemoryContext:
    config = load_config(config_path)
    repo_root = find_git_root(cwd)
    repository_path = resolve_repo_memory_book_relative_path(
        repo_root, find_ghq_roots()
    )
    repository = repository_path.as_posix()
    manifest = load_context(repo_root)

    if manifest is not None:
        if manifest.repository != repository:
            raise ContextError(
                "memoc context repository does not match the current repository: "
                f"{manifest.repository} != {repository}"
            )
        source_branch = manifest.source_branch
        manifest_exists = True
    else:
        source_branch = infer_selected_branch(
            repo_root,
            config.memory_books_root / repository_path,
        )
        manifest_exists = False

    return ResolvedMemoryContext(
        repo_root=repo_root,
        memory_books_root=config.memory_books_root,
        repository=repository,
        source_branch=source_branch,
        manifest_exists=manifest_exists,
    )


def migrate_context(
    cwd: Path,
    config_path: Path | None = None,
    *,
    branch_name: str | None = None,
) -> ContextMigrationResult:
    """Create context.toml for a legacy setup without changing its symlinks."""

    config = load_config(config_path)
    repo_root = find_git_root(cwd)
    repository_path = resolve_repo_memory_book_relative_path(
        repo_root, find_ghq_roots()
    )
    repository = repository_path.as_posix()
    manifest = load_context(repo_root)

    if manifest is not None:
        if manifest.repository != repository:
            raise ContextError(
                "memoc context repository does not match the current repository: "
                f"{manifest.repository} != {repository}"
            )
        if branch_name is not None:
            get_branch_path(branch_name)
            if branch_name != manifest.source_branch:
                raise MemocError(
                    "context already selects a different branch; "
                    f"use 'memoc branch {branch_name}' to change it"
                )
        context = ResolvedMemoryContext(
            repo_root=repo_root,
            memory_books_root=config.memory_books_root,
            repository=repository,
            source_branch=manifest.source_branch,
            manifest_exists=True,
        )
        return ContextMigrationResult(
            context=context,
            migrated=False,
            source_branch_origin="manifest",
        )

    if branch_name is None:
        source_branch, source_branch_origin = infer_selected_branch_with_origin(
            repo_root,
            config.memory_books_root / repository_path,
        )
    else:
        get_branch_path(branch_name)
        source_branch = branch_name
        source_branch_origin = "argument"

    write_context(
        repo_root,
        MemoryContext(
            repository=repository,
            source_branch=source_branch,
        ),
    )
    context = ResolvedMemoryContext(
        repo_root=repo_root,
        memory_books_root=config.memory_books_root,
        repository=repository,
        source_branch=source_branch,
        manifest_exists=True,
    )
    return ContextMigrationResult(
        context=context,
        migrated=True,
        source_branch_origin=source_branch_origin,
    )


def resolve_local_service(
    cwd: Path,
    config_path: Path | None = None,
) -> tuple[ResolvedMemoryContext, MemoryService]:
    context = resolve_memory_context(cwd, config_path)
    store = LocalFilesystemStore(context.memory_books_root)
    return context, MemoryService(store)


def infer_selected_branch(repo_root: Path, repo_memory_book_path: Path) -> str:
    source_branch, _ = infer_selected_branch_with_origin(
        repo_root, repo_memory_book_path
    )
    return source_branch


def infer_selected_branch_with_origin(
    repo_root: Path, repo_memory_book_path: Path
) -> tuple[str, str]:
    branch_link = repo_root / ".memoc" / "branch"
    if branch_link.is_symlink():
        try:
            raw_target = branch_link.readlink()
            target = (
                raw_target
                if raw_target.is_absolute()
                else branch_link.parent / raw_target
            )
            normalized_target = Path(os.path.abspath(target))
            branch_root = Path(os.path.abspath(repo_memory_book_path / "branch"))
            relative_branch = normalized_target.relative_to(branch_root).as_posix()
            get_branch_path(relative_branch)
            return relative_branch, "legacy_symlink"
        except (OSError, ValueError, MemocError):
            pass
    return find_current_branch(repo_root), "git_branch"


def resolve_scope_branch(
    scope: NoteScope,
    requested_branch: str | None,
    context: ResolvedMemoryContext,
) -> str | None:
    if scope is NoteScope.SHARE:
        if requested_branch is not None:
            raise MemocError("--branch cannot be used with share scope")
        return None
    return requested_branch or context.source_branch


def context_payload(context: ResolvedMemoryContext) -> dict[str, object]:
    return {
        "schema_version": 1,
        "repository": context.repository,
        "source_branch": context.source_branch,
        "backend": "filesystem",
        "manifest_path": str(get_context_path(context.repo_root)),
        "manifest_exists": context.manifest_exists,
    }


def note_summary_payload(summary: NoteSummary) -> dict[str, object]:
    return {
        "path": summary.ref.path,
        "version": summary.version,
        "size": summary.size,
    }


def path_access_payload(path: Path) -> dict[str, object]:
    try:
        exists = path.exists()
        return {
            "path": str(path),
            "exists": exists,
            "readable": exists and os.access(path, os.R_OK),
            "writable": exists and os.access(path, os.W_OK),
        }
    except OSError as exc:
        return {
            "path": str(path),
            "exists": False,
            "readable": False,
            "writable": False,
            "error": str(exc),
        }


def symlink_payload(path: Path) -> dict[str, object]:
    is_symlink = path.is_symlink()
    target: str | None = None
    error: str | None = None
    if is_symlink:
        try:
            target = str(path.readlink())
        except OSError as exc:
            error = str(exc)
    try:
        target_exists = path.exists()
    except OSError as exc:
        target_exists = False
        error = str(exc)
    payload: dict[str, object] = {
        "path": str(path),
        "is_symlink": is_symlink,
        "target": target,
        "target_exists": target_exists,
    }
    if error is not None:
        payload["error"] = error
    return payload


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def resolve_repo_memory_book_path(cwd: Path, config_path: Path | None = None) -> Path:
    config = load_config(config_path)
    repo_root = find_git_root(cwd)
    ghq_roots = find_ghq_roots()
    relative_repo_path = resolve_repo_memory_book_relative_path(repo_root, ghq_roots)

    memory_books_root = config.memory_books_root
    if memory_books_root.exists() and not memory_books_root.is_dir():
        raise MemocError(
            f"memory_books_root exists but is not a directory: {memory_books_root}"
        )
    try:
        memory_books_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MemocError(
            f"could not create memory_books_root: {memory_books_root}\n{exc}"
        ) from exc

    return memory_books_root / relative_repo_path


def find_git_root(cwd: Path) -> Path:
    output = run_command(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if not output:
        raise MemocError("could not determine git repository root")
    return Path(output.splitlines()[0]).expanduser().resolve()


def find_ghq_roots() -> list[Path]:
    try:
        output = run_command(["ghq", "root"])
    except MemocError:
        return []
    roots = [Path(line).expanduser().resolve() for line in output.splitlines() if line]
    return roots


def find_current_branch(cwd: Path) -> str:
    output = run_command(["git", "branch", "--show-current"], cwd=cwd)
    branch_name = output.splitlines()[0] if output else ""
    if not branch_name:
        raise MemocError("could not determine current Git branch")
    return branch_name


def resolve_repo_memory_book_relative_path(
    repo_root: Path, ghq_roots: list[Path]
) -> Path:
    relative_repo_path = get_repo_path_under_ghq(repo_root, ghq_roots)
    if relative_repo_path:
        return relative_repo_path

    common_worktree_root = find_common_worktree_root(repo_root)
    if common_worktree_root:
        relative_repo_path = get_repo_path_under_ghq(common_worktree_root, ghq_roots)
        if relative_repo_path:
            return relative_repo_path

    relative_repo_path = get_repo_path_from_origin_remote(repo_root)
    if relative_repo_path:
        return relative_repo_path

    roots_text = ", ".join(str(root) for root in ghq_roots) or "none"
    raise MemocError(
        "could not determine repository memory-book path. "
        f"Repository is not under ghq root ({roots_text}), "
        "its common worktree is not under ghq, and origin remote could not be parsed."
    )


def get_repo_path_under_ghq(repo_root: Path, ghq_roots: list[Path]) -> Path | None:
    for ghq_root in ghq_roots:
        try:
            return repo_root.relative_to(ghq_root)
        except ValueError:
            continue

    return None


def find_common_worktree_root(cwd: Path) -> Path | None:
    output = run_command(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd
    )
    if not output:
        return None

    common_dir = Path(output.splitlines()[0]).expanduser().resolve()
    if common_dir.name != ".git":
        return None
    return common_dir.parent


def get_repo_path_from_origin_remote(cwd: Path) -> Path | None:
    try:
        remote_url = run_command(["git", "remote", "get-url", "origin"], cwd=cwd)
    except MemocError:
        return None
    return parse_remote_repo_path(remote_url)


def parse_remote_repo_path(remote_url: str) -> Path | None:
    remote_url = remote_url.strip()
    if not remote_url:
        return None

    host = ""
    raw_path = ""
    if "://" in remote_url:
        parsed = urlparse(remote_url)
        host = parsed.hostname or ""
        raw_path = parsed.path
    else:
        match = re.match(r"^(?:[^@/]+@)?([^:]+):(.+)$", remote_url)
        if match:
            host = match.group(1)
            raw_path = match.group(2)

    if not host or not raw_path:
        return None

    path_parts = [part for part in raw_path.strip("/").split("/") if part]
    if len(path_parts) < 2:
        return None

    path_parts[-1] = re.sub(r"\.git$", "", path_parts[-1])
    if any(part in {".", "..", ""} for part in path_parts):
        return None

    return Path(host.lower(), *path_parts)


def get_branch_path(branch_name: str) -> Path:
    try:
        branch_path = validate_logical_path(branch_name, label="branch name")
    except InvalidNoteReferenceError as exc:
        raise MemocError(
            f"branch name cannot be used as a directory path: {branch_name}"
        ) from exc
    return Path(*branch_path.parts)


def create_local_memoc_links(
    repo_root: Path,
    repo_memory_book_path: Path,
    branch_memory_book_path: Path,
    all_branches_path: Path | None = None,
) -> None:
    local_memoc_path = repo_root / ".memoc"
    if local_memoc_path.is_symlink() or (
        local_memoc_path.exists() and not local_memoc_path.is_dir()
    ):
        raise MemocError(
            f"local memoc path exists but is not a directory: {local_memoc_path}"
        )

    local_memoc_path.mkdir(parents=True, exist_ok=True)
    create_or_replace_symlink(
        local_memoc_path / "share", repo_memory_book_path / "share"
    )
    create_or_replace_symlink(local_memoc_path / "branch", branch_memory_book_path)

    branches_link_path = local_memoc_path / "branches"
    if all_branches_path:
        create_or_replace_symlink(branches_link_path, all_branches_path)
    elif branches_link_path.is_symlink():
        branches_link_path.unlink()


def create_or_replace_symlink(link_path: Path, target_path: Path) -> None:
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.exists():
        raise MemocError(f"local memoc path exists but is not a symlink: {link_path}")

    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except OSError as exc:
        raise MemocError(
            f"could not create symlink: {link_path} -> {target_path}\n{exc}"
        ) from exc


def run_command(command: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MemocError(f"command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip()
        message = f"command failed: {' '.join(command)}"
        if details:
            message = f"{message}\n{details}"
        raise MemocError(message) from exc

    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except (ConfigError, ContextError, MemoryStoreError, MemocError) as exc:
        if getattr(args, "json", False):
            code = getattr(exc, "code", "memoc_error")
            error: dict[str, object] = {
                "code": code,
                "message": str(exc),
            }
            if isinstance(exc, VersionConflictError):
                error["expected_version"] = exc.expected_version
                error["actual_version"] = exc.actual_version
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": error,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        else:
            print(f"memoc: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
