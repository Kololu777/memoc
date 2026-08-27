from __future__ import annotations

import json
import sys
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from memory_core.cli import init_branch_memory_book, main
from memory_core.config import Config
from memory_core.context import get_context_path, load_context


class NoteCliTests(TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        temporary_root = Path(self.temporary_directory.name)
        self.ghq_root = temporary_root / "ghq"
        self.repo_root = self.ghq_root / "github.com" / "owner" / "repo"
        self.memory_books_root = temporary_root / "memory-books"
        self.repo_root.mkdir(parents=True)

        self.patch_stack = ExitStack()
        self.addCleanup(self.patch_stack.close)
        self.patch_stack.enter_context(
            patch(
                "memory_core.cli.load_config",
                return_value=Config(memory_books_root=self.memory_books_root),
            )
        )
        self.patch_stack.enter_context(
            patch("memory_core.cli.find_git_root", return_value=self.repo_root)
        )
        self.patch_stack.enter_context(
            patch("memory_core.cli.find_ghq_roots", return_value=[self.ghq_root])
        )
        self.patch_stack.enter_context(
            patch("memory_core.cli.find_current_branch", return_value="git-main")
        )

        init_branch_memory_book(self.repo_root, branch_name="feature/foo")

    def run_cli(
        self,
        arguments: list[str],
        *,
        stdin: str = "",
    ) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with (
            patch.object(sys, "stdin", StringIO(stdin)),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_branch_initialization_writes_selected_context(self) -> None:
        context = load_context(self.repo_root)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.repository, "github.com/owner/repo")
        self.assertEqual(context.source_branch, "feature/foo")
        self.assertTrue(get_context_path(self.repo_root).is_file())
        self.assertFalse(get_context_path(self.repo_root).is_symlink())

    def test_context_reports_selected_memory_branch_as_json(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["context", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["repository"], "github.com/owner/repo")
        self.assertEqual(payload["source_branch"], "feature/foo")
        self.assertEqual(payload["backend"], "filesystem")
        self.assertTrue(payload["manifest_exists"])

    def test_share_note_create_list_read_and_versioned_update(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["write", "share", "project.md", "--json"],
            stdin="first\n",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        created = json.loads(stdout)
        self.assertTrue(created["created"])

        exit_code, stdout, stderr = self.run_cli(["list", "share", "--json"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        listed = json.loads(stdout)
        self.assertEqual([note["path"] for note in listed["notes"]], ["project.md"])
        self.assertEqual(listed["notes"][0]["version"], created["version"])

        exit_code, stdout, stderr = self.run_cli(
            ["read", "share", "project.md", "--json"]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        read = json.loads(stdout)
        self.assertEqual(read["content"], "first\n")
        self.assertEqual(read["version"], created["version"])

        exit_code, stdout, stderr = self.run_cli(
            [
                "write",
                "share",
                "project.md",
                "--expected-version",
                created["version"],
                "--json",
            ],
            stdin="second\n",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        updated = json.loads(stdout)
        self.assertFalse(updated["created"])
        self.assertNotEqual(updated["version"], created["version"])

        note_path = (
            self.memory_books_root
            / "github.com"
            / "owner"
            / "repo"
            / "share"
            / "project.md"
        )
        self.assertEqual(note_path.read_text(encoding="utf-8"), "second\n")

    def test_branch_scope_defaults_to_selected_context_branch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["write", "branch", "todo.md", "--json"],
            stdin="todo\n",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["source_branch"], "feature/foo")
        branch_note_path = (
            self.memory_books_root
            / "github.com"
            / "owner"
            / "repo"
            / "branch"
            / "feature"
            / "foo"
            / "todo.md"
        )
        self.assertEqual(branch_note_path.read_text(encoding="utf-8"), "todo\n")

    def test_write_without_version_is_create_only(self) -> None:
        self.run_cli(
            ["write", "share", "existing.md", "--json"],
            stdin="first\n",
        )

        exit_code, stdout, stderr = self.run_cli(
            ["write", "share", "existing.md", "--json"],
            stdin="blind overwrite\n",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "note_already_exists")

    def test_note_commands_do_not_require_local_symlinks(self) -> None:
        (self.repo_root / ".memoc" / "share").unlink()
        (self.repo_root / ".memoc" / "branch").unlink()

        exit_code, stdout, stderr = self.run_cli(
            ["write", "share", "without-links.md", "--json"],
            stdin="available\n",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        created = json.loads(stdout)
        exit_code, stdout, stderr = self.run_cli(
            ["read", "share", "without-links.md", "--json"]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["version"], created["version"])

    def test_stale_update_returns_structured_json_error(self) -> None:
        _, stdout, _ = self.run_cli(
            ["write", "share", "project.md", "--json"],
            stdin="first\n",
        )
        created = json.loads(stdout)
        self.run_cli(
            [
                "write",
                "share",
                "project.md",
                "--expected-version",
                created["version"],
                "--json",
            ],
            stdin="second\n",
        )

        exit_code, stdout, stderr = self.run_cli(
            [
                "write",
                "share",
                "project.md",
                "--expected-version",
                created["version"],
                "--json",
            ],
            stdin="stale\n",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        error = json.loads(stderr)
        self.assertFalse(error["ok"])
        self.assertEqual(error["error"]["code"], "version_conflict")
        self.assertEqual(error["error"]["expected_version"], created["version"])
        self.assertNotEqual(error["error"]["actual_version"], created["version"])

    def test_share_scope_rejects_branch_override(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["list", "share", "--branch", "main", "--json"]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "memoc_error")

    def test_doctor_reports_manifest_storage_and_links(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["doctor", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["manifest_exists"])
        self.assertTrue(payload["memory_book"]["exists"])
        self.assertTrue(payload["share"]["exists"])
        self.assertTrue(payload["source_branch_memory"]["exists"])
        self.assertTrue(payload["links"]["share"]["is_symlink"])
        self.assertTrue(payload["links"]["branch"]["is_symlink"])

    def test_legacy_symlink_context_is_inferred_without_following_target(self) -> None:
        get_context_path(self.repo_root).unlink()

        exit_code, stdout, stderr = self.run_cli(["context", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertFalse(payload["manifest_exists"])
        self.assertEqual(payload["source_branch"], "feature/foo")

    def test_migrate_creates_context_from_legacy_symlink_without_relinking(self) -> None:
        get_context_path(self.repo_root).unlink()
        branch_link = self.repo_root / ".memoc" / "branch"
        original_target = branch_link.readlink()

        exit_code, stdout, stderr = self.run_cli(["migrate", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["migrated"])
        self.assertTrue(payload["manifest_exists"])
        self.assertEqual(payload["source_branch"], "feature/foo")
        self.assertEqual(payload["source_branch_origin"], "legacy_symlink")
        self.assertEqual(branch_link.readlink(), original_target)

        context = load_context(self.repo_root)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.source_branch, "feature/foo")

    def test_migrate_is_idempotent_when_context_exists(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["migrate", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertFalse(payload["migrated"])
        self.assertEqual(payload["source_branch_origin"], "manifest")
        self.assertEqual(payload["source_branch"], "feature/foo")

    def test_migrate_accepts_explicit_branch_when_context_is_missing(self) -> None:
        get_context_path(self.repo_root).unlink()
        (self.repo_root / ".memoc" / "branch").unlink()

        exit_code, stdout, stderr = self.run_cli(
            ["migrate", "--branch", "agent/session", "--json"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["migrated"])
        self.assertEqual(payload["source_branch"], "agent/session")
        self.assertEqual(payload["source_branch_origin"], "argument")

    def test_migrate_does_not_change_an_existing_context_branch(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["migrate", "--branch", "main", "--json"]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        payload = json.loads(stderr)
        self.assertEqual(payload["error"]["code"], "memoc_error")
        self.assertIn("memoc branch main", payload["error"]["message"])
