from __future__ import annotations

from memory_core.store import (
    MemoryStore,
    Note,
    NoteRef,
    NoteScope,
    NoteSummary,
    WriteResult,
)


class MemoryService:
    """Application-facing note operations shared by CLI and future transports."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def list_notes(
        self,
        *,
        repository: str,
        scope: NoteScope | str,
        source_branch: str | None = None,
        prefix: str = "",
    ) -> list[NoteSummary]:
        return self.store.list(
            repository=repository,
            scope=scope,
            source_branch=source_branch,
            prefix=prefix,
        )

    def read_note(self, ref: NoteRef) -> Note:
        return self.store.read(ref)

    def write_note(
        self,
        ref: NoteRef,
        content: str,
        *,
        expected_version: str | None,
    ) -> WriteResult:
        return self.store.write(
            ref,
            content,
            expected_version=expected_version,
        )
