配置・scope・context
====================

論理モデル
----------

ノートは :class:`~memory_core.NoteRef` で指定します。filesystem の絶対パスは
公開 API に含めません。

.. code-block:: python

   from memory_core import NoteRef

   shared = NoteRef(
       repository="github.com/acme/widget",
       scope="share",
       path="design/plan.md",
   )

   branch_only = NoteRef(
       repository="github.com/acme/widget",
       scope="branch",
       source_branch="feature/search",
       path="todo.md",
   )

.. list-table:: scope の意味
   :header-rows: 1
   :widths: 18 32 50

   * - scope
     - ``source_branch``
     - 用途
   * - ``share``
     - 必ず ``None``
     - repository の全 branch で共有する情報
   * - ``branch``
     - 必須
     - 特定の source branch にだけ属する作業情報

保存レイアウト
--------------

既存の配置規則は変更しません。``repository``、``source_branch``、``path`` は
``/`` 区切りの論理パスとして、次のように filesystem へ写像されます。

.. code-block:: text

   <memory_books_root>/
   └── github.com/acme/widget/
       ├── share/
       │   ├── project.md
       │   └── design/plan.md
       └── branch/
           ├── main/todo.md
           └── feature/search/todo.md

対応関係は次のとおりです。

.. code-block:: text

   NoteRef(repository="github.com/acme/widget",
           scope="share",
           path="design/plan.md")
       -> github.com/acme/widget/share/design/plan.md

   NoteRef(repository="github.com/acme/widget",
           scope="branch",
           source_branch="feature/search",
           path="todo.md")
       -> github.com/acme/widget/branch/feature/search/todo.md

global config
-------------

標準の設定ファイルは ``~/.config/memoc/config.toml`` です。

.. code-block:: toml

   memory_books_root = "/home/alice/memory-books"

設定の優先順位は次のとおりです。

#. ``MEMOC_MEMORY_BOOKS_ROOT``
#. CLI の ``--config /path/to/config.toml``
#. ``MEMOC_CONFIG`` が指す config file
#. ``~/.config/memoc/config.toml``

``memory_books_root`` 環境変数が設定されている場合、config file は読みません。
標準または指定された config file が存在しない場合、memoc は空の template を作成し、
``memory_books_root`` の設定を求めて終了します。

.. code-block:: console

   $ MEMOC_MEMORY_BOOKS_ROOT=/srv/private-memory memoc context
   repository: github.com/acme/widget
   source_branch: main
   backend: filesystem
   manifest: /work/widget/.memoc/context.toml

repository の決定方法
---------------------

source repository から ``github.com/acme/widget`` のような論理 ``repository`` を
次の順序で決定します。

#. Git root が ``ghq root`` の配下なら、ghq root からの相対パスを使う
#. 外部 worktree なら、Git common directory の repository が ghq 配下か調べる
#. どちらでもなければ ``origin`` URL を解析する

例えば ``/home/alice/ghq/github.com/acme/widget`` と、その repository から作った
外部 worktree は、どちらも ``github.com/acme/widget`` に解決されます。

local context manifest
----------------------

``memoc branch`` は source repository 内に ``.memoc/context.toml`` を通常ファイルとして
atomic に生成します。

.. code-block:: toml

   schema_version = 1
   repository = "github.com/acme/widget"
   source_branch = "feature/search"

各 field の契約は次のとおりです。

``schema_version``
   現在は整数 ``1`` のみを受け付けます。

``repository``
   source repository の論理名です。現在の repository 解決結果と一致しなければ
   ``context_error`` になります。

``source_branch``
   branch scope の default です。現在 checkout 中の Git branch と異なっていても
   構いません。

manifest 自体が symlink の場合は拒否します。machine 固有の
``memory_books_root`` や credential は manifest に保存しません。

legacy checkout の fallback
----------------------------

既存 checkout に ``context.toml`` がない場合も動作します。

#. ``.memoc/branch`` が symlink なら、そのリンク文字列から branch を推論する
#. 推論できなければ現在 checkout 中の Git branch を使う

この fallback で返す ``context --json`` の ``manifest_exists`` は ``false`` です。
選択 branch を変えずに manifest だけ生成するには ``memoc migrate --json`` を使います。
``memoc migrate`` は legacy symlink のリンク文字列を読みますが、target directory を
辿ったり symlink を張り直したりしません。選択 branch を意図的に変更する場合は
``memoc branch <name>`` を使います。

symlink との関係
----------------

``memoc branch`` は互換性のため、従来どおり以下も作成します。

.. code-block:: text

   .memoc/share  -> <memory_books_root>/github.com/acme/widget/share
   .memoc/branch -> <memory_books_root>/github.com/acme/widget/branch/main

``memoc branch --all`` の場合は、さらに次を作ります。

.. code-block:: text

   .memoc/branches -> <memory_books_root>/github.com/acme/widget/branch

ただし ``context`` / ``list`` / ``read`` / ``write`` / ``doctor`` は note 操作のために
これらの symlink を辿りません。config の ``memory_books_root`` と論理参照から保存先を
直接組み立てます。

.. warning::

   symlink 非依存は filesystem 権限の回避を意味しません。process 自体が
   ``memory_books_root`` を読めない sandbox では、現在の local backend は使えません。
   remote backend の境界については :doc:`backend` を参照してください。
