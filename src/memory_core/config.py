from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


CONFIG_ENV_VAR = "MEMOC_CONFIG"
MEMORY_BOOKS_ROOT_ENV_VAR = "MEMOC_MEMORY_BOOKS_ROOT"
DEFAULT_CONFIG_CONTENT = """# Path to your private memory-books repository.
memory_books_root = ""
"""


class ConfigError(RuntimeError):
    """Raised when memoc configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    memory_books_root: Path


def default_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base_path = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base_path / "memoc" / "config.toml"


def load_config(config_path: Path | None = None) -> Config:
    env_root = os.environ.get(MEMORY_BOOKS_ROOT_ENV_VAR)
    if env_root:
        return Config(memory_books_root=Path(env_root).expanduser().resolve())

    path = config_path or default_config_path()
    created = ensure_config_file(path)

    try:
        with path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in config file: {path}: {exc}") from exc

    memory_books_root = raw_config.get("memory_books_root")
    if not isinstance(memory_books_root, str) or not memory_books_root.strip():
        if created:
            raise ConfigError(
                f"created config file: {path}\n"
                "Set memory_books_root to your private memory-books repository path."
            )
        raise ConfigError(f"missing memory_books_root in config file: {path}")

    return Config(memory_books_root=Path(memory_books_root).expanduser().resolve())


def ensure_config_file(path: Path) -> bool:
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")
    return True
