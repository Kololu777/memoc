from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from memory_core.context import (
    ContextError,
    MemoryContext,
    get_context_path,
    load_context,
    write_context,
)


class MemoryContextTests(TestCase):
    def test_round_trips_context_as_regular_toml_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            context = MemoryContext(
                repository="github.com/owner/repo",
                source_branch="feature/foo",
            )

            path = write_context(repo_root, context)

            self.assertEqual(path, get_context_path(repo_root))
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "schema_version = 1\n"
                'repository = "github.com/owner/repo"\n'
                'source_branch = "feature/foo"\n',
            )
            self.assertEqual(load_context(repo_root), context)

    def test_returns_none_when_context_does_not_exist(self) -> None:
        with TemporaryDirectory() as tmpdir:
            self.assertIsNone(load_context(Path(tmpdir)))

    def test_replaces_existing_context(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            write_context(
                repo_root,
                MemoryContext(
                    repository="github.com/owner/repo",
                    source_branch="main",
                ),
            )

            write_context(
                repo_root,
                MemoryContext(
                    repository="github.com/owner/repo",
                    source_branch="agent",
                ),
            )

            context = load_context(repo_root)
            self.assertIsNotNone(context)
            assert context is not None
            self.assertEqual(context.source_branch, "agent")

    def test_rejects_invalid_context_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            context_path = repo_root / ".memoc" / "context.toml"
            context_path.parent.mkdir()
            context_path.write_text(
                "schema_version = 99\n"
                'repository = "github.com/owner/repo"\n'
                'source_branch = "main"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContextError, "schema_version"):
                load_context(repo_root)

    def test_rejects_context_symlink(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            target = repo_root / "target.toml"
            target.write_text("", encoding="utf-8")
            context_path = repo_root / ".memoc" / "context.toml"
            context_path.parent.mkdir()
            context_path.symlink_to(target)

            with self.assertRaisesRegex(ContextError, "regular file"):
                load_context(repo_root)
