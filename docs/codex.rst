Codex から使う
===============

推奨境界
--------

Codex は note 本文を ``.memoc/share`` や ``.memoc/branch`` へ直接書かず、CLI の
machine-readable API を使います。

.. code-block:: text

   Codex -> memoc context/list/read/write --json
         -> MemoryService
         -> LocalFilesystemStore

symlink は human workflow と旧版互換のために残ります。agent workflow では
``context.toml`` を起点に論理参照を組み立てます。

標準 workflow
-------------

#. context を確認する。
#. legacy checkout なら一度だけ migrate する。
#. JSON で一覧または本文と version を取得する。
#. 新規作成、または version を指定した更新を行う。

.. code-block:: console

   $ memoc context --json
   {"manifest_exists":false,"repository":"github.com/acme/widget","source_branch":"main",...}

   $ memoc migrate --json
   {"manifest_exists":true,"migrated":true,"source_branch_origin":"legacy_symlink",...}

   $ memoc read share project.md --json
   {"content":"# Project\n","version":"sha256:4c5b...",...}

   $ memoc write share project.md \
       --expected-version 'sha256:4c5b...' --json < prepared-note.md

``version_conflict`` では最新 version だけを差し替えて再試行しません。再度 read し、
変更内容を reconcile してから更新します。

CLI と skill の同時配布
-----------------------

Nix package は executable と次の skill source を同じ output に含めます。

.. code-block:: text

   $out/bin/memoc
   $out/share/memoc/skills/memoc-create/
   $out/share/memoc/skills/memoc-write/

Home Manager module を import すると、その同一 package から CLI と Codex skill を
install できます。

.. code-block:: nix

   {
     imports = [ inputs.memoc.homeManagerModules.default ];
     programs.memoc.enable = true;
   }

canonical path は ``~/.codex/skills/memoc-create`` と
``~/.codex/skills/memoc-write`` です。同名 skill は merge されないため、例えば
``~/.codex/skills/share/memoc-write`` のような別コピーを同時に install しません。

権限
----

``memoc`` subprocess が ``memory_books_root`` を読み書きできる環境では、MCP や
GraphQL backend は不要です。Codex の writable root または限定 command approval で
CLI に必要な権限だけを与えます。local filesystem access 自体を付与できない環境でのみ、
:doc:`backend` の remote 境界を使います。
