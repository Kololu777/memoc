from __future__ import annotations

import json
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from memory_core.store import InvalidNoteReferenceError, validate_logical_path

CONTEXT_SCHEMA_VERSION = 1
CONTEXT_FILENAME = "context.toml"


class ContextError(RuntimeError):
    """Raised when local .memoc context cannot be read or written."""

    code = "context_error"


@dataclass(frozen=True)
class MemoryContext:
    repository: str
    source_branch: str
    schema_version: int = CONTEXT_SCHEMA_VERSION


def get_context_path(repo_root: Path) -> Path:
    return repo_root / ".memoc" / CONTEXT_FILENAME


def load_context(repo_root: Path) -> MemoryContext | None:
    path = get_context_path(repo_root)
    if path.is_symlink():
        raise ContextError(f"memoc context is not a regular file: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise ContextError(f"memoc context is not a regular file: {path}")

    try:
        with path.open("rb") as context_file:
            raw_context = tomllib.load(context_file)
    except tomllib.TOMLDecodeError as exc:
        raise ContextError(f"invalid TOML in memoc context: {path}: {exc}") from exc
    except OSError as exc:
        raise ContextError(f"could not read memoc context: {path}\n{exc}") from exc

    schema_version = raw_context.get("schema_version")
    repository = raw_context.get("repository")
    source_branch = raw_context.get("source_branch")

    if type(schema_version) is not int or schema_version != CONTEXT_SCHEMA_VERSION:
        raise ContextError(
            f"unsupported memoc context schema_version in {path}: {schema_version}"
        )
    if not isinstance(repository, str):
        raise ContextError(f"missing repository in memoc context: {path}")
    if not isinstance(source_branch, str):
        raise ContextError(f"missing source_branch in memoc context: {path}")

    _validate_context_path(repository, "repository", path)
    _validate_context_path(source_branch, "source_branch", path)
    return MemoryContext(
        schema_version=schema_version,
        repository=repository,
        source_branch=source_branch,
    )


def write_context(repo_root: Path, context: MemoryContext) -> Path:
    path = get_context_path(repo_root)
    memoc_path = path.parent
    if memoc_path.is_symlink() or (memoc_path.exists() and not memoc_path.is_dir()):
        raise ContextError(f"local memoc path is not a directory: {memoc_path}")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ContextError(f"memoc context is not a regular file: {path}")

    if context.schema_version != CONTEXT_SCHEMA_VERSION:
        raise ContextError(
            f"unsupported memoc context schema_version: {context.schema_version}"
        )
    try:
        validate_logical_path(context.repository, label="repository")
        validate_logical_path(context.source_branch, label="source_branch")
    except InvalidNoteReferenceError as exc:
        raise ContextError(str(exc)) from exc

    try:
        memoc_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ContextError(
            f"could not create local memoc path: {memoc_path}\n{exc}"
        ) from exc
    contents = (
        f"schema_version = {context.schema_version}\n"
        f"repository = {json.dumps(context.repository, ensure_ascii=False)}\n"
        f"source_branch = {json.dumps(context.source_branch, ensure_ascii=False)}\n"
    )

    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{CONTEXT_FILENAME}.",
            suffix=".tmp",
            dir=memoc_path,
        )
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise ContextError(f"could not write memoc context: {path}\n{exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return path


def _validate_context_path(value: str, field: str, path: Path) -> None:
    try:
        validate_logical_path(value, label=field)
    except InvalidNoteReferenceError as exc:
        raise ContextError(f"invalid {field} in memoc context {path}: {exc}") from exc
