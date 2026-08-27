"""Public storage and service API for memoc."""

from memory_core.service import MemoryService
from memory_core.store import (
    InvalidNoteReferenceError,
    LocalFilesystemStore,
    MemoryCollectionNotFoundError,
    MemoryStore,
    MemoryStoreError,
    Note,
    NoteAlreadyExistsError,
    NoteNotFoundError,
    NoteRef,
    NoteScope,
    NoteSummary,
    StoreUnavailableError,
    VersionConflictError,
    WriteResult,
)

__version__ = "0.2.0"

__all__ = [
    "InvalidNoteReferenceError",
    "LocalFilesystemStore",
    "MemoryCollectionNotFoundError",
    "MemoryService",
    "MemoryStore",
    "MemoryStoreError",
    "Note",
    "NoteAlreadyExistsError",
    "NoteNotFoundError",
    "NoteRef",
    "NoteScope",
    "NoteSummary",
    "StoreUnavailableError",
    "VersionConflictError",
    "WriteResult",
    "__version__",
]
