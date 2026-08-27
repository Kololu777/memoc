Python API
==========

公開 entry point
----------------

利用者向けの型は ``memory_core`` package から import できます。

.. testcode:: public_imports

   from memory_core import (
       LocalFilesystemStore,
       MemoryService,
       MemoryStore,
       Note,
       NoteRef,
       NoteScope,
       NoteSummary,
       WriteResult,
   )

通常は :class:`~memory_core.MemoryService` に backend を渡し、service 経由で操作します。
CLI も同じ境界を使用します。

``NoteRef``
-----------

:class:`~memory_core.NoteRef` は不変 dataclass です。``scope`` は文字列
``"share"`` / ``"branch"`` または :class:`~memory_core.NoteScope` を受け取り、内部で
enum に正規化します。

共有ノートの例です。

.. testcode:: note_ref

   from memory_core import NoteRef, NoteScope

   ref = NoteRef(
       repository="github.com/acme/widget",
       scope="share",
       path="design/plan.md",
   )

   assert ref.scope is NoteScope.SHARE
   assert ref.source_branch is None

branch ノートでは ``source_branch`` が必須です。

.. testcode:: note_ref

   branch_ref = NoteRef(
       repository="github.com/acme/widget",
       scope=NoteScope.BRANCH,
       source_branch="feature/search",
       path="todo.md",
   )

次は契約違反なので :class:`~memory_core.InvalidNoteReferenceError` になります。

.. code-block:: python

   NoteRef(
       repository="github.com/acme/widget",
       scope="share",
       source_branch="main",  # share では指定禁止
       path="project.md",
   )

返却 model
----------

.. list-table:: model fields
   :header-rows: 1
   :widths: 22 28 50

   * - 型
     - field
     - 意味
   * - :class:`~memory_core.Note`
     - ``ref``, ``content``, ``version``, ``size``
     - 読んだ UTF-8 本文、opaque version、byte size
   * - :class:`~memory_core.NoteSummary`
     - ``ref``, ``version``, ``size``
     - list 用の本文を含まない概要
   * - :class:`~memory_core.WriteResult`
     - ``ref``, ``version``, ``created``
     - write 後の version と新規作成かどうか

``size`` は Python の文字数ではなく、UTF-8 encoding 後の byte 数です。

.. testcode:: byte_size

   content = "メモ\n"
   assert len(content) == 3
   assert len(content.encode("utf-8")) == 7

``LocalFilesystemStore`` の完全な例
-----------------------------------

次の例は、空の一時 directory に collection を初期化し、create、read、update、list を
順に行います。

.. testcode:: filesystem_store

   from pathlib import Path
   from tempfile import TemporaryDirectory

   from memory_core import LocalFilesystemStore, MemoryService, NoteRef

   with TemporaryDirectory() as temporary_directory:
       root = Path(temporary_directory)
       repository = "github.com/acme/widget"

       # Store は collection 自体を暗黙作成しない。
       (root / repository / "share").mkdir(parents=True)

       service = MemoryService(LocalFilesystemStore(root))
       ref = NoteRef(
           repository=repository,
           scope="share",
           path="design/plan.md",
       )

       created = service.write_note(
           ref,
           "first\n",
           expected_version=None,
       )
       assert created.created is True
       assert created.version.startswith("sha256:")

       note = service.read_note(ref)
       assert note.content == "first\n"
       assert note.version == created.version
       assert note.size == 6

       updated = service.write_note(
           ref,
           "second\n",
           expected_version=note.version,
       )
       assert updated.created is False
       assert updated.version != note.version

       summaries = service.list_notes(
           repository=repository,
           scope="share",
           prefix="design",
       )
       assert [summary.ref.path for summary in summaries] == ["design/plan.md"]

実際の repository では collection directory は ``memoc init`` / ``memoc branch`` が
作成します。Store を直接使う場合は、上の例のように呼び出し側が collection を用意します。

branch scope の例
-----------------

``feature/search`` のような slash を含む branch は nested directory へ写像されます。

.. testcode:: branch_store

   from pathlib import Path
   from tempfile import TemporaryDirectory

   from memory_core import LocalFilesystemStore, MemoryService, NoteRef

   with TemporaryDirectory() as temporary_directory:
       root = Path(temporary_directory)
       repository = "github.com/acme/widget"
       (root / repository / "branch" / "feature" / "search").mkdir(parents=True)
       service = MemoryService(LocalFilesystemStore(root))

       ref = NoteRef(
           repository=repository,
           scope="branch",
           source_branch="feature/search",
           path="todo.md",
       )
       result = service.write_note(ref, "- verify query\n", expected_version=None)

       assert result.ref.source_branch == "feature/search"
       assert (
           root
           / "github.com/acme/widget/branch/feature/search/todo.md"
       ).read_text(encoding="utf-8") == "- verify query\n"

``MemoryStore`` contract
------------------------

:class:`~memory_core.MemoryStore` は structural typing 用の Protocol です。
実装 class が継承する必要はありませんが、次の method 契約を満たす必要があります。

.. code-block:: python

   class MemoryStore(Protocol):
       def list(
           self,
           *,
           repository: str,
           scope: NoteScope | str,
           source_branch: str | None = None,
           prefix: str = "",
       ) -> list[NoteSummary]: ...

       def read(self, ref: NoteRef) -> Note: ...

       def write(
           self,
           ref: NoteRef,
           content: str,
           *,
           expected_version: str | None,
       ) -> WriteResult: ...

``expected_version`` は keyword-only かつ必須引数です。値 ``None`` は
「version check をしない」ではなく **create-only** を意味します。

例外を扱う
----------

version conflict では期待値と実値を個別に取得できます。

.. code-block:: python

   from memory_core import VersionConflictError

   original = service.read_note(ref)

   # 別 writer が先に更新したとする。
   service.write_note(ref, "newer\n", expected_version=original.version)

   try:
       service.write_note(ref, "stale\n", expected_version=original.version)
   except VersionConflictError as error:
       print(error.expected_version)
       print(error.actual_version)

create-only の重複は別の例外です。

.. code-block:: python

   from memory_core import NoteAlreadyExistsError

   try:
       service.write_note(ref, "replacement\n", expected_version=None)
   except NoteAlreadyExistsError:
       print("既存ノートは変更されていない")

例外一覧と安全性の詳細は :doc:`consistency` を参照してください。

API reference
-------------

.. autoclass:: memory_core.NoteRef
   :members:

.. autoclass:: memory_core.Note
   :members:

.. autoclass:: memory_core.NoteSummary
   :members:

.. autoclass:: memory_core.WriteResult
   :members:

.. autoclass:: memory_core.MemoryStore
   :members:

.. autoclass:: memory_core.MemoryService
   :members:

.. autoclass:: memory_core.LocalFilesystemStore
   :members:
