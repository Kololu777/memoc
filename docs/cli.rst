CLI リファレンス
================

基本形
------

.. code-block:: console

   $ memoc [--config CONFIG] COMMAND [OPTIONS]

``--config`` は subcommand より前に指定します。

.. code-block:: console

   $ memoc --config ./memoc.toml context --json

``--json`` 対応 command は、成功時に JSON を stdout、実行時エラーを stderr へ
出力します。通常の成功は exit code ``0``、memoc が捕捉したエラーは ``1`` です。
引数解析自体のエラーは argparse の usage と exit code ``2`` になります。

``memoc init``
--------------

現在の source repository に対応する repository memory book と ``share`` directory を
作成します。

.. code-block:: console

   $ memoc init
   /home/alice/memory-books/github.com/acme/widget

作成後の例です。

.. code-block:: text

   /home/alice/memory-books/github.com/acme/widget/
   └── share/

``init`` 単独では branch directory、local symlink、``context.toml`` を作成しません。
通常は続けて ``memoc branch`` を実行します。

``memoc branch``
----------------

branch memory を作成し、local symlink と context manifest を更新します。
branch 名を省略すると、現在 checkout 中の Git branch を使います。

.. code-block:: console

   $ git branch --show-current
   main
   $ memoc branch
   /home/alice/memory-books/github.com/acme/widget/branch/main

任意の source branch を Git checkout せずに選択することもできます。

.. code-block:: console

   $ memoc branch feature/search
   /home/alice/memory-books/github.com/acme/widget/branch/feature/search

この例では ``.memoc/branch`` と ``context.toml`` の ``source_branch`` が
``feature/search`` を指します。現在の Git branch と一致する必要はありません。

``--all`` を付けると、全 branch memory を参照する symlink も作ります。

.. code-block:: console

   $ memoc branch feature/search --all
   /home/alice/memory-books/github.com/acme/widget/branch/feature/search
   $ readlink .memoc/branches
   /home/alice/memory-books/github.com/acme/widget/branch

後で ``--all`` なしの ``memoc branch`` を実行すると、memoc が作った
``.memoc/branches`` symlink は削除されます。

``memoc context``
-----------------

現在の source repository と、branch scope の default を表示します。

.. code-block:: console

   $ memoc context
   repository: github.com/acme/widget
   source_branch: feature/search
   backend: filesystem
   manifest: /work/widget/.memoc/context.toml

機械可読形式の例です。JSON は説明のため整形しています。

.. code-block:: console

   $ memoc context --json

.. code-block:: json

   {
     "backend": "filesystem",
     "manifest_exists": true,
     "manifest_path": "/work/widget/.memoc/context.toml",
     "repository": "github.com/acme/widget",
     "schema_version": 1,
     "source_branch": "feature/search"
   }

manifest がまだない legacy checkout では ``manifest_exists`` が ``false`` になり、
source branch は既存 symlink または現在の Git branch から推論されます。

``memoc migrate``
-----------------

旧版で初期化済みの checkout に、通常ファイルの ``.memoc/context.toml`` を追加します。
既存 symlink や memory-book directory は変更しません。

.. code-block:: console

   $ memoc migrate --json

.. code-block:: json

   {
     "backend": "filesystem",
     "manifest_exists": true,
     "manifest_path": "/work/widget/.memoc/context.toml",
     "migrated": true,
     "repository": "github.com/acme/widget",
     "schema_version": 1,
     "source_branch": "feature/search",
     "source_branch_origin": "legacy_symlink"
   }

2 回目以降は ``migrated`` が ``false``、``source_branch_origin`` が ``manifest``
となるため、繰り返し実行できます。

legacy symlink がなく、記録すべき branch が既知の場合は明示します。

.. code-block:: console

   $ memoc migrate --branch main --json

既存 manifest と異なる ``--branch`` は拒否します。選択 branch を変える操作は migration
ではなく ``memoc branch <name>`` です。

``memoc list``
--------------

指定 scope のノートを再帰的に、path の昇順で一覧します。

.. code-block:: console

   $ memoc list share
   commands.md
   design/plan.md
   project.md

branch scope は context の ``source_branch`` を default にします。

.. code-block:: console

   $ memoc list branch
   session.md
   todo.md

別の branch を明示できます。

.. code-block:: console

   $ memoc list branch --branch main
   release/checklist.md

scope の後の任意 positional argument は path prefix です。directory prefix なら配下を
再帰表示し、file path ならその file だけを返します。存在しない prefix は空の一覧です。

.. code-block:: console

   $ memoc list share design
   design/architecture.md
   design/plan.md

JSON では各 note の opaque version と byte size も返します。

.. code-block:: console

   $ memoc list share design --json

.. code-block:: json

   {
     "notes": [
       {
         "path": "design/architecture.md",
         "size": 412,
         "version": "sha256:1f73..."
       },
       {
         "path": "design/plan.md",
         "size": 128,
         "version": "sha256:8ab2..."
       }
     ],
     "prefix": "design",
     "repository": "github.com/acme/widget",
     "scope": "share",
     "source_branch": null
   }

``share`` に ``--branch`` を指定するのはエラーです。

.. code-block:: console

   $ memoc list share --branch main --json
   {"error":{"code":"memoc_error","message":"--branch cannot be used with share scope"},"ok":false}

``memoc read``
--------------

UTF-8 note を読みます。通常出力は保存された本文そのもので、末尾 newline を追加しません。

.. code-block:: console

   $ memoc read share project.md
   # Project

   Current decisions.

branch scope の例です。

.. code-block:: console

   $ memoc read branch todo.md --branch feature/search
   - add remote backend

``--json`` では、更新に使う version と UTF-8 byte size を取得できます。

.. code-block:: console

   $ memoc read share project.md --json

.. code-block:: json

   {
     "content": "# Project\n\nCurrent decisions.\n",
     "path": "project.md",
     "repository": "github.com/acme/widget",
     "scope": "share",
     "size": 30,
     "source_branch": null,
     "version": "sha256:4c5b..."
   }

存在しない note は ``note_not_found`` です。

.. code-block:: console

   $ memoc read share missing.md --json
   {"error":{"code":"note_not_found","message":"note not found: /home/alice/memory-books/github.com/acme/widget/share/missing.md"},"ok":false}

``memoc write``
---------------

stdin の UTF-8 text をそのまま保存します。write には二つの mode しかありません。

.. list-table:: write mode
   :header-rows: 1
   :widths: 28 28 44

   * - ``--expected-version``
     - 意味
     - 既存 note に対する動作
   * - 省略
     - create-only
     - ``note_already_exists`` で拒否
   * - 指定
     - version checked update
     - 一致時だけ更新。不一致は ``version_conflict``

新規作成の例です。

.. code-block:: console

   $ printf '# Runbook\n\nStart here.\n' | memoc write share runbook.md
   created runbook.md sha256:8d12...

同じ command をもう一度実行しても上書きしません。

.. code-block:: console

   $ printf 'replacement\n' | memoc write share runbook.md --json
   {"error":{"code":"note_already_exists","message":"note already exists: /home/alice/memory-books/github.com/acme/widget/share/runbook.md"},"ok":false}

安全な更新は read、編集、write の順です。次の shell 例では ``jq`` で version を
取り出しています。

.. code-block:: bash

   current="$(memoc read share runbook.md --json)"
   version="$(printf '%s' "$current" | jq -r .version)"
   printf '# Runbook\n\nUpdated safely.\n' |
     memoc write share runbook.md --expected-version "$version" --json

成功結果の例です。

.. code-block:: json

   {
     "created": false,
     "path": "runbook.md",
     "repository": "github.com/acme/widget",
     "scope": "share",
     "source_branch": null,
     "version": "sha256:21d9..."
   }

``version`` は opaque token として扱ってください。現在の local backend は
``sha256:<hex>`` ですが、caller は prefix や長さを解析してはいけません。

branch note の作成例です。

.. code-block:: console

   $ printf -- '- investigate cache\n' | memoc write branch todo.md
   created todo.md sha256:f813...
   $ printf -- '- prepare release\n' | memoc write branch todo.md --branch main
   created todo.md sha256:31a0...

``memoc doctor``
----------------

context、local storage、従来 symlink の状態を **変更せず** に調べます。

.. code-block:: console

   $ memoc doctor
   repository: github.com/acme/widget
   source_branch: main
   manifest_exists: true
   memory_book: exists=true readable=true writable=true
   share_link: symlink=true target_exists=true
   branch_link: symlink=true target_exists=true
   branches_link: symlink=false target_exists=false

``--json`` では path と各判定値を個別に取得できます。

.. code-block:: json

   {
     "backend": "filesystem",
     "manifest_exists": true,
     "manifest_path": "/work/widget/.memoc/context.toml",
     "repository": "github.com/acme/widget",
     "schema_version": 1,
     "source_branch": "main",
     "memory_book": {
       "path": "/home/alice/memory-books/github.com/acme/widget",
       "exists": true,
       "readable": true,
       "writable": true
     },
     "share": {
       "path": "/home/alice/memory-books/github.com/acme/widget/share",
       "exists": true,
       "readable": true,
       "writable": true
     },
     "source_branch_memory": {
       "path": "/home/alice/memory-books/github.com/acme/widget/branch/main",
       "exists": true,
       "readable": true,
       "writable": true
     },
     "links": {
       "share": {
         "path": "/work/widget/.memoc/share",
         "is_symlink": true,
         "target": "/home/alice/memory-books/github.com/acme/widget/share",
         "target_exists": true
       },
       "branch": {
         "path": "/work/widget/.memoc/branch",
         "is_symlink": true,
         "target": "/home/alice/memory-books/github.com/acme/widget/branch/main",
         "target_exists": true
       },
       "branches": {
         "path": "/work/widget/.memoc/branches",
         "is_symlink": false,
         "target": null,
         "target_exists": false
       }
     }
   }

``doctor`` の ``readable`` / ``writable`` は process から見た ``os.access`` の結果です。
symlink が壊れていても、それだけで note command が失敗するとは限りません。
