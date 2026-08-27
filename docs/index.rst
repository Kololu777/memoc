memoc 仕様書
============

memoc は、Git repository ごとの Markdown ノートを ``memory-books`` に保存し、
repository 共通のメモと branch 固有のメモを扱う CLI / Python library です。

この文書は **memory-core 0.2.0 の現行実装** を仕様としてまとめています。

.. important::

   現在実装されている backend は :class:`~memory_core.LocalFilesystemStore` です。
   ``GitHubGraphQLStore`` や MCP transport は未実装です。ただし、それらを追加するための
   :class:`~memory_core.MemoryStore` 境界は実装済みです。

現在できること
--------------

* ``share`` と ``branch`` の論理アドレスでノートを指定する
* ``.memoc`` の symlink を経由せずに ``list`` / ``read`` / ``write`` する
* SHA-256 version を使い、読み取り後に変化したノートの上書きを拒否する
* 新規作成時の blind overwrite を拒否する
* ``context.toml`` から repository と対象 branch を復元する
* legacy symlink-only checkout を ``migrate`` で context manifest へ移行する
* ``doctor --json`` で manifest、保存先、従来 symlink を診断する
* 従来の ``init`` / ``branch`` / symlink workflow を継続利用する

最短の例
--------

まず保存先を設定し、現在の Git branch 用 memory book を初期化します。

.. code-block:: console

   $ export MEMOC_MEMORY_BOOKS_ROOT=/home/alice/memory-books
   $ memoc branch
   /home/alice/memory-books/github.com/acme/widget/branch/main

新しい共有ノートを作成します。``--expected-version`` を省略した write は
**新規作成専用** です。

.. code-block:: console

   $ printf '# Project\n\nFirst note.\n' | memoc write share project.md
   created project.md sha256:4c5b...

本文と version を読みます。

.. code-block:: console

   $ memoc read share project.md --json
   {"content":"# Project\n\nFirst note.\n","path":"project.md","repository":"github.com/acme/widget","scope":"share","size":23,"source_branch":null,"version":"sha256:4c5b..."}

更新時は、read で得た version を明示します。

.. code-block:: console

   $ printf '# Project\n\nUpdated.\n' | memoc write share project.md \
       --expected-version 'sha256:4c5b...'
   updated project.md sha256:9a71...

同じ古い version をもう一度使うと ``version_conflict`` になり、現在の内容は
変更されません。詳しくは :doc:`consistency` を参照してください。

仕様一覧
--------

.. toctree::
   :maxdepth: 2
   :caption: Contents

   concepts
   cli
   codex
   python-api
   consistency
   backend
