from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from memory_core.service import MemoryService
from memory_core.store import (
    InvalidNoteReferenceError,
    LocalFilesystemStore,
    MemoryCollectionNotFoundError,
    NoteAlreadyExistsError,
    NoteNotFoundError,
    NoteRef,
    NoteScope,
    VersionConflictError,
)


class SynchronizingFilesystemStore(LocalFilesystemStore):
    def __init__(self, memory_books_root: Path, barrier: object) -> None:
        super().__init__(memory_books_root)
        self.barrier = barrier

    def _write_temporary(self, note_path: Path, content: bytes) -> Path:
        temporary_path = super()._write_temporary(note_path, content)
        self.barrier.wait(timeout=5)  # type: ignore[attr-defined]
        return temporary_path


def run_concurrent_update(
    memory_books_root: str,
    expected_version: str,
    content: str,
    barrier: object,
    results: object,
) -> None:
    service = MemoryService(
        SynchronizingFilesystemStore(Path(memory_books_root), barrier)
    )
    ref = NoteRef(
        repository="github.com/owner/repo",
        scope=NoteScope.SHARE,
        path="concurrent.md",
    )
    try:
        result = service.write_note(
            ref,
            content,
            expected_version=expected_version,
        )
        results.put(("updated", result.version))  # type: ignore[attr-defined]
    except VersionConflictError as exc:
        results.put(("conflict", exc.actual_version))  # type: ignore[attr-defined]


class LocalFilesystemStoreTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.memory_books_root = Path(self.temporary_directory.name)
        self.repository = "github.com/owner/repo"
        self.repository_path = self.memory_books_root / self.repository
        (self.repository_path / "share").mkdir(parents=True)
        (self.repository_path / "branch" / "feature" / "foo").mkdir(parents=True)
        self.service = MemoryService(LocalFilesystemStore(self.memory_books_root))

    def test_accepts_public_string_scope_values(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope="share",
            path="project.md",
        )

        self.assertIs(ref.scope, NoteScope.SHARE)
        self.service.write_note(ref, "content\n", expected_version=None)
        summaries = self.service.list_notes(
            repository=self.repository,
            scope="share",
        )
        self.assertEqual([summary.ref.path for summary in summaries], ["project.md"])

    def test_creates_reads_lists_and_updates_share_note(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="design/plan.md",
        )

        created = self.service.write_note(ref, "first\n", expected_version=None)

        self.assertTrue(created.created)
        self.assertTrue(created.version.startswith("sha256:"))
        note = self.service.read_note(ref)
        self.assertEqual(note.content, "first\n")
        self.assertEqual(note.version, created.version)
        self.assertEqual(note.size, 6)

        summaries = self.service.list_notes(
            repository=self.repository,
            scope=NoteScope.SHARE,
        )
        self.assertEqual(
            [summary.ref.path for summary in summaries], ["design/plan.md"]
        )
        self.assertEqual(summaries[0].version, created.version)

        updated = self.service.write_note(
            ref,
            "second\n",
            expected_version=created.version,
        )

        self.assertFalse(updated.created)
        self.assertNotEqual(updated.version, created.version)
        self.assertEqual(self.service.read_note(ref).content, "second\n")
        note_path = self.repository_path / "share" / "design" / "plan.md"
        temporary_files = list(note_path.parent.glob(f".{note_path.name}.*.tmp"))
        self.assertEqual(temporary_files, [])

    def test_lists_only_requested_prefix_in_path_order(self) -> None:
        share_path = self.repository_path / "share"
        (share_path / "z.md").write_text("z", encoding="utf-8")
        (share_path / "design").mkdir()
        (share_path / "design" / "b.md").write_text("b", encoding="utf-8")
        (share_path / "design" / "a.md").write_text("a", encoding="utf-8")

        summaries = self.service.list_notes(
            repository=self.repository,
            scope=NoteScope.SHARE,
            prefix="design",
        )

        self.assertEqual(
            [summary.ref.path for summary in summaries],
            ["design/a.md", "design/b.md"],
        )

    def test_supports_nested_source_branch(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.BRANCH,
            source_branch="feature/foo",
            path="todo.md",
        )

        result = self.service.write_note(ref, "todo\n", expected_version=None)

        self.assertTrue(result.created)
        self.assertEqual(self.service.read_note(ref).content, "todo\n")
        self.assertTrue(
            (self.repository_path / "branch" / "feature" / "foo" / "todo.md").is_file()
        )

    def test_create_does_not_overwrite_existing_note(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="project.md",
        )
        self.service.write_note(ref, "original", expected_version=None)

        with self.assertRaises(NoteAlreadyExistsError):
            self.service.write_note(ref, "replacement", expected_version=None)

        self.assertEqual(self.service.read_note(ref).content, "original")

    def test_update_rejects_stale_version_without_changing_note(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="project.md",
        )
        created = self.service.write_note(ref, "original", expected_version=None)
        updated = self.service.write_note(
            ref,
            "current",
            expected_version=created.version,
        )

        with self.assertRaises(VersionConflictError) as raised:
            self.service.write_note(
                ref,
                "stale replacement",
                expected_version=created.version,
            )

        self.assertEqual(raised.exception.actual_version, updated.version)
        self.assertEqual(self.service.read_note(ref).content, "current")

    @skipUnless(os.name == "posix", "requires POSIX advisory locks")
    def test_concurrent_updates_allow_only_one_matching_version(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="concurrent.md",
        )
        created = self.service.write_note(ref, "original", expected_version=None)
        process_context = multiprocessing.get_context("fork")
        barrier = process_context.Barrier(2)
        results = process_context.Queue()
        processes = [
            process_context.Process(
                target=run_concurrent_update,
                args=(
                    str(self.memory_books_root),
                    created.version,
                    content,
                    barrier,
                    results,
                ),
            )
            for content in ("first", "second")
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join()

        self.assertEqual([process.exitcode for process in processes], [0, 0])
        outcomes = [results.get(timeout=1), results.get(timeout=1)]
        self.assertEqual(
            sorted(outcome[0] for outcome in outcomes), ["conflict", "updated"]
        )
        versions = {outcome[1] for outcome in outcomes}
        self.assertEqual(len(versions), 1)

    def test_update_requires_existing_note(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="missing/note.md",
        )

        with self.assertRaises(NoteNotFoundError):
            self.service.write_note(
                ref,
                "content",
                expected_version="sha256:missing",
            )

        self.assertFalse((self.repository_path / "share" / "missing").exists())

    def test_requires_initialized_collection(self) -> None:
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.BRANCH,
            source_branch="missing",
            path="todo.md",
        )

        with self.assertRaises(MemoryCollectionNotFoundError):
            self.service.write_note(ref, "todo", expected_version=None)

    def test_rejects_unsafe_logical_paths(self) -> None:
        invalid_references = [
            {"repository": "../repo", "scope": NoteScope.SHARE, "path": "a.md"},
            {
                "repository": self.repository,
                "scope": NoteScope.SHARE,
                "path": "../a.md",
            },
            {
                "repository": self.repository,
                "scope": NoteScope.BRANCH,
                "source_branch": "../main",
                "path": "a.md",
            },
            {
                "repository": self.repository,
                "scope": NoteScope.SHARE,
                "source_branch": "main",
                "path": "a.md",
            },
        ]

        for reference in invalid_references:
            with (
                self.subTest(reference=reference),
                self.assertRaises(InvalidNoteReferenceError),
            ):
                NoteRef(**reference)

    def test_rejects_note_symlink_that_escapes_memory_books_root(self) -> None:
        outside_note = self.memory_books_root.parent / "outside.md"
        outside_note.write_text("outside", encoding="utf-8")
        link_path = self.repository_path / "share" / "linked.md"
        link_path.symlink_to(outside_note)
        ref = NoteRef(
            repository=self.repository,
            scope=NoteScope.SHARE,
            path="linked.md",
        )

        with self.assertRaises(InvalidNoteReferenceError):
            self.service.read_note(ref)
