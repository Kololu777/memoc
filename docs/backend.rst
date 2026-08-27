backend 拡張境界
================

現在の構成
----------

note 操作は次の依存方向です。

.. code-block:: text

   CLI command
       |
       v
   MemoryService
       |
       v
   MemoryStore Protocol
       |
       v
   LocalFilesystemStore

:class:`~memory_core.MemoryService` は filesystem path や symlink を知りません。
:class:`~memory_core.NoteRef` と :class:`~memory_core.MemoryStore` の model だけを扱います。

.. important::

   現在の CLI wiring は ``LocalFilesystemStore`` を直接選択します。Store 境界は実装済みですが、
   backend selector、GitHub authentication、GraphQL client、MCP server はまだありません。
   remote backend を追加する際は Store 実装に加えて CLI の backend 選択も追加します。

置き換え可能であることの例
----------------------------

``MemoryStore`` は Protocol なので、継承なしで同じ method を実装できます。次は version を
整数 revision として持つ最小の in-memory backend です。

.. testcode:: in_memory_backend

   from memory_core import (
       MemoryService,
       Note,
       NoteAlreadyExistsError,
       NoteNotFoundError,
       NoteRef,
       NoteScope,
       NoteSummary,
       VersionConflictError,
       WriteResult,
   )


   class InMemoryStore:
       def __init__(self) -> None:
           self._notes: dict[NoteRef, tuple[str, int]] = {}

       def list(
           self,
           *,
           repository: str,
           scope: NoteScope | str,
           source_branch: str | None = None,
           prefix: str = "",
       ) -> list[NoteSummary]:
           normalized_scope = NoteScope(scope)
           matches = []
           for ref, (content, revision) in self._notes.items():
               if ref.repository != repository or ref.scope is not normalized_scope:
                   continue
               matches_prefix = (
                   not prefix
                   or ref.path == prefix
                   or ref.path.startswith(f"{prefix}/")
               )
               if ref.source_branch != source_branch or not matches_prefix:
                   continue
               matches.append(
                   NoteSummary(
                       ref=ref,
                       version=f"memory:{revision}",
                       size=len(content.encode("utf-8")),
                   )
               )
           return sorted(matches, key=lambda summary: summary.ref.path)

       def read(self, ref: NoteRef) -> Note:
           try:
               content, revision = self._notes[ref]
           except KeyError as error:
               raise NoteNotFoundError(f"note not found: {ref.path}") from error
           return Note(
               ref=ref,
               content=content,
               version=f"memory:{revision}",
               size=len(content.encode("utf-8")),
           )

       def write(
           self,
           ref: NoteRef,
           content: str,
           *,
           expected_version: str | None,
       ) -> WriteResult:
           current = self._notes.get(ref)
           if expected_version is None:
               if current is not None:
                   raise NoteAlreadyExistsError(f"note already exists: {ref.path}")
               revision = 1
               created = True
           else:
               if current is None:
                   raise NoteNotFoundError(f"note not found: {ref.path}")
               actual_version = f"memory:{current[1]}"
               if actual_version != expected_version:
                   raise VersionConflictError(expected_version, actual_version)
               revision = current[1] + 1
               created = False

           self._notes[ref] = (content, revision)
           return WriteResult(
               ref=ref,
               version=f"memory:{revision}",
               created=created,
           )


   store = InMemoryStore()
   service = MemoryService(store)
   ref = NoteRef(
       repository="github.com/acme/widget",
       scope="share",
       path="project.md",
   )

   created = service.write_note(ref, "first\n", expected_version=None)
   note = service.read_note(ref)
   updated = service.write_note(
       ref,
       "second\n",
       expected_version=note.version,
   )

   assert created.version == "memory:1"
   assert updated.version == "memory:2"

この backend の version は ``sha256:`` ではありません。それでも service が動くことが、
version を opaque にする理由です。

remote backend が守る契約
-------------------------

GitHub GraphQL、REST、database、MCP bridge などへ置き換える場合も、少なくとも次を保ちます。

論理参照
   ``repository`` / ``scope`` / ``source_branch`` / ``path`` の意味と validation を維持する。

読み取り
   UTF-8 text、opaque version、UTF-8 byte size を一つの :class:`~memory_core.Note` として返す。

新規作成
   ``expected_version=None`` は create-only。既存 note を上書きしない。

更新
   caller が読んだ version と現在 version が一致するときだけ write する。比較から commit までを
   backend が提供できる最も狭い atomic / transactional primitive で保護する。

一覧
   path prefix を受け取り、安定した path 順で :class:`~memory_core.NoteSummary` を返す。

エラー
   :doc:`consistency` の exception taxonomy へ変換し、transport 固有 error を CLI まで漏らさない。

GitHub backend の version 例
--------------------------------

GitHub 上の blob OID を version token として使う backend なら、caller 側は次のように扱います。

.. code-block:: python

   note = github_service.read_note(ref)
   print(note.version)  # 例: "github-blob:abc123..."

   github_service.write_note(
       ref,
       edited_content,
       expected_version=note.version,
   )

実装側は note の blob version だけでなく、remote branch 更新時の競合も検出しなければなりません。
競合を検出した場合は :class:`~memory_core.VersionConflictError` へ変換します。

.. note::

   ``github-blob:`` はこの文書上の例であり、確定した wire format ではありません。
   ``GitHubGraphQLStore`` の version format は、その backend を実装するときに決定します。

MCP を置く場所
--------------

MCP は Store 実装にも、service を公開する transport にもできます。

.. code-block:: text

   agent -> MCP tools -> MemoryService -> LocalFilesystemStore

   agent -> MCP tools -> MemoryService -> GitHubGraphQLStore

例えば MCP tool の ``read_note`` は tool argument から ``NoteRef`` を構築し、service の
結果を JSON へ直します。

.. code-block:: json

   {
     "repository": "github.com/acme/widget",
     "scope": "branch",
     "source_branch": "feature/search",
     "path": "todo.md"
   }

この形なら agent process が ``memory_books_root`` を直接 mount できなくても、MCP server
または GitHub API にアクセスできる場所で note 操作を実行できます。
