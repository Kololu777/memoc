# memory-core

`memory-core` は、リポジトリごとのメモ帳である `memory-books` を操作するためのコアエンジンです。

`memory-books` 自体は private GitHub repository として管理し、`ghq` で clone しておく想定です。`memoc init` は現在の `ghq` 管理下の Git repository に対応するメモ帳ディレクトリを、`memory-books` 配下に同じ階層で作成します。

## Requirements

- Python 3.12 以上
- Git
- ghq

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Configuration

`memory-books` の root path はユーザー設定として `~/.config/memoc/config.toml` に書きます。初回実行時に設定ファイルがなければ、`memoc init` が雛形を作成します。

```toml
memory_books_root = "/home/ko/ghq/github.com/your-name/memory-books"
```

環境変数で一時的に上書きすることもできます。

```bash
export MEMOC_MEMORY_BOOKS_ROOT=/home/ko/ghq/github.com/your-name/memory-books
```

設定ファイルの場所を変えたい場合は `MEMOC_CONFIG` または `memoc --config` を使えます。

## Usage

```bash
memoc init
```

例えば、現在の repository が次の場所にあるとします。

```text
/home/ko/ghq/github.com/foo/bar
```

設定が次の値なら、

```toml
memory_books_root = "/home/ko/ghq/github.com/your-name/memory-books"
```

`memoc init` は次のディレクトリを作成します。

```text
/home/ko/ghq/github.com/your-name/memory-books/github.com/foo/bar
```

## Project Structure

```text
.
├── main.py
├── pyproject.toml
├── README.md
└── src/
    └── memory_core/
        ├── __init__.py
        ├── cli.py
        └── config.py
```

## Development Notes

- 依存関係を追加したら `pyproject.toml` に反映します。
- `memory_books_root` は存在するディレクトリである必要があります。`memory-books` repository は先に clone してください。
