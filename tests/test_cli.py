from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from memory_core.cli import (
    MemocError,
    find_ghq_roots,
    init_branch_memory_book,
    init_memory_book,
    parse_remote_repo_path,
)
from memory_core.config import Config


class InitMemoryBookTests(TestCase):
    def test_creates_missing_memory_books_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                target_path = init_memory_book(repo_root)

            self.assertEqual(
                target_path, memory_books_root / "github.com" / "owner" / "repo"
            )
            self.assertTrue(memory_books_root.is_dir())
            self.assertTrue(target_path.is_dir())
            self.assertTrue((target_path / "share").is_dir())

    def test_uses_common_worktree_root_under_ghq(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            main_repo_root = ghq_root / "github.com" / "owner" / "repo"
            worktree_root = tmp_path / "worktrees" / "repo-feature"
            memory_books_root = tmp_path / "memory-books"
            main_repo_root.mkdir(parents=True)
            worktree_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=worktree_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
                patch(
                    "memory_core.cli.find_common_worktree_root",
                    return_value=main_repo_root,
                ),
            ):
                target_path = init_memory_book(worktree_root)

            self.assertEqual(
                target_path, memory_books_root / "github.com" / "owner" / "repo"
            )
            self.assertTrue((target_path / "share").is_dir())

    def test_uses_origin_remote_when_repo_is_not_under_ghq(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = tmp_path / "worktrees" / "repo-feature"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
                patch("memory_core.cli.find_common_worktree_root", return_value=None),
                patch(
                    "memory_core.cli.get_repo_path_from_origin_remote",
                    return_value=Path("github.com") / "owner" / "repo",
                ),
            ):
                target_path = init_memory_book(repo_root)

            self.assertEqual(
                target_path, memory_books_root / "github.com" / "owner" / "repo"
            )
            self.assertTrue((target_path / "share").is_dir())

    def test_parses_origin_remote_paths(self) -> None:
        expected_path = Path("github.com") / "owner" / "repo"

        self.assertEqual(
            parse_remote_repo_path("https://github.com/owner/repo.git"),
            expected_path,
        )
        self.assertEqual(
            parse_remote_repo_path("git@github.com:owner/repo.git"),
            expected_path,
        )

    def test_find_ghq_roots_returns_empty_when_ghq_is_unavailable(self) -> None:
        with patch("memory_core.cli.run_command", side_effect=MemocError("missing")):
            self.assertEqual(find_ghq_roots(), [])

    def test_creates_current_branch_memory_book(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
                patch("memory_core.cli.find_current_branch", return_value="main"),
            ):
                target_path = init_branch_memory_book(repo_root)

            repo_memory_book_path = memory_books_root / "github.com" / "owner" / "repo"
            self.assertEqual(target_path, repo_memory_book_path / "branch" / "main")
            self.assertTrue((repo_memory_book_path / "share").is_dir())
            self.assertTrue(target_path.is_dir())
            self.assertEqual(
                (repo_root / ".memoc" / "share").resolve(),
                (repo_memory_book_path / "share").resolve(),
            )
            self.assertTrue((repo_root / ".memoc" / "share").is_symlink())
            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(), target_path.resolve()
            )
            self.assertTrue((repo_root / ".memoc" / "branch").is_symlink())

    def test_creates_named_branch_memory_book(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                target_path = init_branch_memory_book(
                    repo_root, branch_name="feature/foo"
                )

            self.assertEqual(
                target_path,
                memory_books_root
                / "github.com"
                / "owner"
                / "repo"
                / "branch"
                / "feature"
                / "foo",
            )
            self.assertTrue(target_path.is_dir())
            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(), target_path.resolve()
            )

    def test_updates_local_branch_symlink(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                init_branch_memory_book(repo_root, branch_name="main")
                target_path = init_branch_memory_book(
                    repo_root, branch_name="feature/foo"
                )

            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(), target_path.resolve()
            )

    def test_exposes_all_branch_memory_books(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
                patch("memory_core.cli.find_current_branch", return_value="agent"),
            ):
                init_branch_memory_book(repo_root, branch_name="main")
                init_branch_memory_book(repo_root, branch_name="feature/foo")
                target_path = init_branch_memory_book(
                    repo_root, expose_all_branches=True
                )

            branch_root_path = (
                memory_books_root / "github.com" / "owner" / "repo" / "branch"
            )
            self.assertEqual(target_path, branch_root_path / "agent")
            self.assertTrue(target_path.is_dir())
            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(),
                branch_root_path.resolve(),
            )
            self.assertTrue((repo_root / ".memoc" / "branch" / "main").is_dir())
            self.assertTrue(
                (repo_root / ".memoc" / "branch" / "feature" / "foo").is_dir()
            )
            self.assertTrue((repo_root / ".memoc" / "branch" / "agent").is_dir())

    def test_narrows_branch_link_after_exposing_all(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
                patch("memory_core.cli.find_current_branch", return_value="agent"),
            ):
                init_branch_memory_book(repo_root, branch_name="main")
                init_branch_memory_book(repo_root, branch_name="feature/foo")
                init_branch_memory_book(repo_root, expose_all_branches=True)
                main_target_path = init_branch_memory_book(repo_root, branch_name="main")

            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(),
                main_target_path.resolve(),
            )
            self.assertFalse((repo_root / ".memoc" / "branch" / "feature").exists())

    def test_creates_named_branch_memory_book_while_exposing_all(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                target_path = init_branch_memory_book(
                    repo_root, branch_name="agent", expose_all_branches=True
                )

            branch_root_path = (
                memory_books_root / "github.com" / "owner" / "repo" / "branch"
            )
            self.assertEqual(target_path, branch_root_path / "agent")
            self.assertTrue(target_path.is_dir())
            self.assertEqual(
                (repo_root / ".memoc" / "branch").resolve(),
                branch_root_path.resolve(),
            )
            self.assertTrue((repo_root / ".memoc" / "branch").is_symlink())
            self.assertTrue((repo_root / ".memoc" / "branch" / "agent").is_dir())

    def test_rejects_existing_local_memoc_path_that_is_not_symlink(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)
            (repo_root / ".memoc").mkdir()
            (repo_root / ".memoc" / "branch").mkdir()

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                with self.assertRaisesRegex(MemocError, "not a symlink"):
                    init_branch_memory_book(repo_root, branch_name="main")

    def test_rejects_memory_books_root_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ghq_root = tmp_path / "ghq"
            repo_root = ghq_root / "github.com" / "owner" / "repo"
            memory_books_root = tmp_path / "memory-books"
            repo_root.mkdir(parents=True)
            memory_books_root.write_text("", encoding="utf-8")

            with (
                patch(
                    "memory_core.cli.load_config",
                    return_value=Config(memory_books_root=memory_books_root),
                ),
                patch("memory_core.cli.find_git_root", return_value=repo_root),
                patch("memory_core.cli.find_ghq_roots", return_value=[ghq_root]),
            ):
                with self.assertRaisesRegex(MemocError, "exists but is not a directory"):
                    init_memory_book(repo_root)
