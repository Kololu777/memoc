from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from memory_core.config import ConfigError, load_config


class MemocError(RuntimeError):
    """Raised when a memoc command cannot complete."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memoc")
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

    return parser


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
    return target_path


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
    if not branch_name:
        raise MemocError("branch name is empty")

    branch_path = Path(branch_name)
    if branch_path.is_absolute() or ".." in branch_path.parts:
        raise MemocError(
            f"branch name cannot be used as a directory path: {branch_name}"
        )
    return branch_path


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
    except (ConfigError, MemocError) as exc:
        print(f"memoc: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
