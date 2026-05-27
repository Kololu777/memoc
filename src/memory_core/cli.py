from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    target_path = init_memory_book(Path.cwd(), args.config)
    print(target_path)
    return 0


def init_memory_book(cwd: Path, config_path: Path | None = None) -> Path:
    config = load_config(config_path)
    repo_root = find_git_root(cwd)
    ghq_roots = find_ghq_roots()
    relative_repo_path = get_repo_path_under_ghq(repo_root, ghq_roots)

    memory_books_root = config.memory_books_root
    if not memory_books_root.is_dir():
        raise MemocError(
            f"memory_books_root does not exist or is not a directory: {memory_books_root}"
        )

    target_path = memory_books_root / relative_repo_path
    target_path.mkdir(parents=True, exist_ok=True)
    return target_path


def find_git_root(cwd: Path) -> Path:
    output = run_command(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if not output:
        raise MemocError("could not determine git repository root")
    return Path(output.splitlines()[0]).expanduser().resolve()


def find_ghq_roots() -> list[Path]:
    output = run_command(["ghq", "root"])
    roots = [Path(line).expanduser().resolve() for line in output.splitlines() if line]
    if not roots:
        raise MemocError("could not determine ghq root")
    return roots


def get_repo_path_under_ghq(repo_root: Path, ghq_roots: list[Path]) -> Path:
    for ghq_root in ghq_roots:
        try:
            return repo_root.relative_to(ghq_root)
        except ValueError:
            continue

    roots_text = ", ".join(str(root) for root in ghq_roots)
    raise MemocError(f"current git repository is not under ghq root: {roots_text}")


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
