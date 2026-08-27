from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]


class MemoryStoreError(RuntimeError):
    """Base class for note storage failures."""

    code = "store_error"


class InvalidNoteReferenceError(MemoryStoreError):
    """Raised when a logical repository, branch, or note path is unsafe."""

    code = "invalid_note_reference"


class MemoryCollectionNotFoundError(MemoryStoreError):
    """Raised when the requested share or branch memory has not been initialized."""

    code = "memory_collection_not_found"


class NoteNotFoundError(MemoryStoreError):
    """Raised when a requested note does not exist."""

    code = "note_not_found"


class NoteAlreadyExistsError(MemoryStoreError):
    """Raised when create-only semantics encounter an existing note."""

    code = "note_already_exists"


class VersionConflictError(MemoryStoreError):
    """Raised when the caller's expected version is stale."""

    code = "version_conflict"

    def __init__(self, expected_version: str, actual_version: str) -> None:
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"note version changed: expected {expected_version}, found {actual_version}"
        )


class StoreUnavailableError(MemoryStoreError):
    """Raised when the configured storage cannot be accessed."""

    code = "store_unavailable"


class NoteScope(StrEnum):
    SHARE = "share"
    BRANCH = "branch"


def _coerce_note_scope(value: object) -> NoteScope:
    if isinstance(value, NoteScope):
        return value
    if isinstance(value, str):
        try:
            return NoteScope(value)
        except ValueError:
            pass
    raise InvalidNoteReferenceError(f"unsupported note scope: {value}")


def validate_logical_path(
    value: str,
    *,
    label: str,
    allow_empty: bool = False,
) -> PurePosixPath:
    """Validate a slash-separated path used inside a memory-books repository."""

    if not isinstance(value, str):
        raise InvalidNoteReferenceError(f"{label} must be a string")
    if not value:
        if allow_empty:
            return PurePosixPath()
        raise InvalidNoteReferenceError(f"{label} is empty")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InvalidNoteReferenceError(f"{label} contains control characters")
    if "\\" in value:
        raise InvalidNoteReferenceError(f"{label} is not a valid logical path: {value}")
    if value.startswith("/") or value.endswith("/"):
        raise InvalidNoteReferenceError(f"{label} is not a valid logical path: {value}")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidNoteReferenceError(f"{label} is not a valid logical path: {value}")

    return PurePosixPath(*parts)


@dataclass(frozen=True, init=False)
class NoteRef:
    repository: str
    scope: NoteScope
    path: str
    source_branch: str | None = None

    def __init__(
        self,
        repository: str,
        scope: NoteScope | str,
        path: str,
        source_branch: str | None = None,
    ) -> None:
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "scope", _coerce_note_scope(scope))
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "source_branch", source_branch)
        self.__post_init__()

    def __post_init__(self) -> None:
        scope = _coerce_note_scope(self.scope)
        validate_logical_path(self.repository, label="repository")
        validate_logical_path(self.path, label="note path")
        if scope is NoteScope.SHARE:
            if self.source_branch is not None:
                raise InvalidNoteReferenceError(
                    "source_branch must be omitted for share notes"
                )
        elif scope is NoteScope.BRANCH:
            if self.source_branch is None:
                raise InvalidNoteReferenceError(
                    "source_branch is required for branch notes"
                )
            validate_logical_path(self.source_branch, label="source branch")
        else:  # pragma: no cover - guarded by _coerce_note_scope
            raise InvalidNoteReferenceError(f"unsupported note scope: {scope}")


@dataclass(frozen=True)
class Note:
    ref: NoteRef
    content: str
    version: str
    size: int


@dataclass(frozen=True)
class NoteSummary:
    ref: NoteRef
    version: str
    size: int


@dataclass(frozen=True)
class WriteResult:
    ref: NoteRef
    version: str
    created: bool


class MemoryStore(Protocol):
    def list(
        self,
        *,
        repository: str,
        scope: NoteScope | str,
        source_branch: str | None = None,
        prefix: str = "",
    ) -> list[NoteSummary]: ...

    def read(self, ref: NoteRef) -> Note: ...

    def write(
        self,
        ref: NoteRef,
        content: str,
        *,
        expected_version: str | None,
    ) -> WriteResult: ...


class LocalFilesystemStore:
    """Store notes below a local memory-books root without using .memoc links."""

    def __init__(self, memory_books_root: Path) -> None:
        self.memory_books_root = memory_books_root.expanduser().resolve()

    def list(
        self,
        *,
        repository: str,
        scope: NoteScope | str,
        source_branch: str | None = None,
        prefix: str = "",
    ) -> list[NoteSummary]:
        collection_path = self._collection_path(repository, scope, source_branch)
        self._require_collection(collection_path)
        prefix_path = validate_logical_path(
            prefix, label="note prefix", allow_empty=True
        )
        search_path = self._safe_path(collection_path, prefix_path)

        if search_path.is_symlink():
            self._reject_symlink(search_path)
        if not search_path.exists():
            return []

        if search_path.is_file():
            paths = [search_path]
        elif search_path.is_dir():
            try:
                paths = sorted(
                    (path for path in search_path.rglob("*") if path.is_file()),
                    key=lambda path: path.relative_to(collection_path).as_posix(),
                )
            except OSError as exc:
                raise StoreUnavailableError(
                    f"could not list memory collection: {collection_path}\n{exc}"
                ) from exc
        else:
            return []

        notes: list[NoteSummary] = []
        for note_path in paths:
            self._reject_symlink(note_path)
            relative_path = note_path.relative_to(collection_path).as_posix()
            ref = NoteRef(
                repository=repository,
                scope=scope,
                source_branch=source_branch,
                path=relative_path,
            )
            content_bytes = self._read_bytes(note_path)
            notes.append(
                NoteSummary(
                    ref=ref,
                    version=self._version(content_bytes),
                    size=len(content_bytes),
                )
            )
        return notes

    def read(self, ref: NoteRef) -> Note:
        collection_path = self._collection_path(
            ref.repository, ref.scope, ref.source_branch
        )
        self._require_collection(collection_path)
        note_path = self._note_path(collection_path, ref.path)
        self._require_note(note_path)
        content_bytes = self._read_bytes(note_path)
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StoreUnavailableError(
                f"note is not valid UTF-8 text: {ref.path}"
            ) from exc
        return Note(
            ref=ref,
            content=content,
            version=self._version(content_bytes),
            size=len(content_bytes),
        )

    def write(
        self,
        ref: NoteRef,
        content: str,
        *,
        expected_version: str | None,
    ) -> WriteResult:
        collection_path = self._collection_path(
            ref.repository, ref.scope, ref.source_branch
        )
        self._require_collection(collection_path)
        note_path = self._note_path(collection_path, ref.path)
        if note_path.is_symlink():
            self._reject_symlink(note_path)

        if not isinstance(content, str):
            raise StoreUnavailableError("note content must be a string")
        content_bytes = content.encode("utf-8")
        if expected_version is None:
            try:
                note_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StoreUnavailableError(
                    f"could not create note parent: {note_path.parent}\n{exc}"
                ) from exc
        else:
            self._require_note(note_path)
        temporary_path = self._write_temporary(note_path, content_bytes)

        try:
            with self._note_lock(note_path):
                if expected_version is None:
                    created = True
                    self._install_new_file(temporary_path, note_path)
                else:
                    created = False
                    self._replace_existing_file(
                        temporary_path,
                        note_path,
                        expected_version=expected_version,
                    )
        finally:
            temporary_path.unlink(missing_ok=True)

        return WriteResult(
            ref=ref,
            version=self._version(content_bytes),
            created=created,
        )

    def _collection_path(
        self,
        repository: str,
        scope: NoteScope | str,
        source_branch: str | None,
    ) -> Path:
        scope = _coerce_note_scope(scope)
        repository_path = validate_logical_path(repository, label="repository")
        if scope is NoteScope.SHARE:
            if source_branch is not None:
                raise InvalidNoteReferenceError(
                    "source_branch must be omitted for share notes"
                )
            relative_path = repository_path / "share"
        elif scope is NoteScope.BRANCH:
            if source_branch is None:
                raise InvalidNoteReferenceError(
                    "source_branch is required for branch notes"
                )
            branch_path = validate_logical_path(source_branch, label="source branch")
            relative_path = repository_path / "branch" / branch_path
        else:  # pragma: no cover - guarded by _coerce_note_scope
            raise InvalidNoteReferenceError(f"unsupported note scope: {scope}")
        return self._safe_path(self.memory_books_root, relative_path)

    def _note_path(self, collection_path: Path, note_path: str) -> Path:
        relative_path = validate_logical_path(note_path, label="note path")
        return self._safe_path(collection_path, relative_path)

    def _safe_path(self, base_path: Path, relative_path: PurePosixPath) -> Path:
        candidate = base_path.joinpath(*relative_path.parts)
        try:
            resolved_candidate = candidate.resolve(strict=False)
            resolved_candidate.relative_to(self.memory_books_root)
        except (OSError, ValueError) as exc:
            raise InvalidNoteReferenceError(
                f"path escapes memory_books_root: {candidate}"
            ) from exc
        return candidate

    def _require_collection(self, collection_path: Path) -> None:
        try:
            if collection_path.is_symlink():
                resolved = collection_path.resolve(strict=True)
                resolved.relative_to(self.memory_books_root)
            mode = collection_path.stat().st_mode
            if not stat.S_ISDIR(mode):
                raise MemoryCollectionNotFoundError(
                    f"memory collection is not initialized: {collection_path}"
                )
        except FileNotFoundError as exc:
            raise MemoryCollectionNotFoundError(
                f"memory collection is not initialized: {collection_path}"
            ) from exc
        except MemoryStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise StoreUnavailableError(
                f"could not access memory collection: {collection_path}\n{exc}"
            ) from exc

    def _require_note(self, note_path: Path) -> None:
        self._reject_symlink(note_path)
        try:
            mode = note_path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise NoteNotFoundError(f"note not found: {note_path}")
        except FileNotFoundError as exc:
            raise NoteNotFoundError(f"note not found: {note_path}") from exc
        except MemoryStoreError:
            raise
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not access note: {note_path}\n{exc}"
            ) from exc

    def _reject_symlink(self, path: Path) -> None:
        try:
            if path.is_symlink():
                raise InvalidNoteReferenceError(
                    f"note paths cannot be symbolic links: {path}"
                )
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not inspect path: {path}\n{exc}"
            ) from exc

    def _read_bytes(self, note_path: Path) -> bytes:
        try:
            return note_path.read_bytes()
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not read note: {note_path}\n{exc}"
            ) from exc

    def _write_temporary(self, note_path: Path, content: bytes) -> Path:
        temporary_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{note_path.name}.",
                suffix=".tmp",
                dir=note_path.parent,
            )
            temporary_path = Path(raw_path)
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            if note_path.exists() and not note_path.is_symlink():
                temporary_path.chmod(note_path.stat().st_mode & 0o777)
            return temporary_path
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise StoreUnavailableError(
                f"could not prepare note write: {note_path}\n{exc}"
            ) from exc

    @contextmanager
    def _note_lock(self, note_path: Path) -> Iterator[None]:
        if fcntl is None:
            yield
            return

        user_id = os.getuid() if hasattr(os, "getuid") else "user"
        lock_root = Path(tempfile.gettempdir()) / f"memoc-{user_id}" / "locks"
        lock_name = hashlib.sha256(str(note_path).encode("utf-8")).hexdigest()
        lock_path = lock_root / f"{lock_name}.lock"
        try:
            lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            with lock_path.open("a+b") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except MemoryStoreError:
            raise
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not lock note for writing: {note_path}\n{exc}"
            ) from exc

    def _install_new_file(self, temporary_path: Path, note_path: Path) -> None:
        try:
            os.link(temporary_path, note_path)
        except FileExistsError as exc:
            raise NoteAlreadyExistsError(f"note already exists: {note_path}") from exc
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not create note: {note_path}\n{exc}"
            ) from exc

    def _replace_existing_file(
        self,
        temporary_path: Path,
        note_path: Path,
        *,
        expected_version: str,
    ) -> None:
        self._require_note(note_path)
        actual_version = self._version(self._read_bytes(note_path))
        if actual_version != expected_version:
            raise VersionConflictError(expected_version, actual_version)
        try:
            os.replace(temporary_path, note_path)
        except OSError as exc:
            raise StoreUnavailableError(
                f"could not replace note: {note_path}\n{exc}"
            ) from exc

    @staticmethod
    def _version(content: bytes) -> str:
        return f"sha256:{hashlib.sha256(content).hexdigest()}"
