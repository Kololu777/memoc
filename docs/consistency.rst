整合性・atomicity・エラー
=========================

version contract
----------------

version は caller が内容の変化を検出するための **opaque token** です。
``LocalFilesystemStore`` は現在、file content の SHA-256 を次の形式で返します。

.. code-block:: text

   sha256:4c5b5a3d...

同じ byte content なら同じ version、1 byte でも異なれば別 version です。caller は
``sha256:`` prefix、長さ、hash algorithm に依存せず、read で得た文字列をそのまま
次の write へ渡します。

.. code-block:: python

   note = service.read_note(ref)
   result = service.write_note(
       ref,
       edited_content,
       expected_version=note.version,
   )

write state table
-----------------

.. list-table:: ``expected_version`` と現在状態
   :header-rows: 1
   :widths: 24 20 28 28

   * - expected version
     - note
     - 結果
     - ``created``
   * - ``None``
     - なし
     - create 成功
     - ``True``
   * - ``None``
     - あり
     - ``note_already_exists``
     - 返却なし
   * - token
     - なし
     - ``note_not_found``
     - 返却なし
   * - token
     - version 一致
     - update 成功
     - ``False``
   * - token
     - version 不一致
     - ``version_conflict``
     - 返却なし

したがって blind overwrite 用 API はありません。現在の内容を知らずに既存 note を
更新することはできません。

競合の例
--------

二つの client が同じ version を読んだ場合、先に書いた一方だけが成功します。

.. code-block:: text

   client A                 store                    client B
      |                       |                         |
      |---- read ------------>|                         |
      |<--- version=v1 -------|                         |
      |                       |<----------- read -------|
      |                       |------------ v1 -------->|
      |---- write(v1) ------->|                         |
      |<--- version=v2 -------|                         |
      |                       |<---------- write(v1) ---|
      |                       |--- version_conflict --->|

CLI の競合エラー例です。

.. code-block:: json

   {
     "error": {
       "actual_version": "sha256:9a71...",
       "code": "version_conflict",
       "expected_version": "sha256:4c5b...",
       "message": "note version changed: expected sha256:4c5b..., found sha256:9a71..."
     },
     "ok": false
   }

このとき stale writer の本文は保存されません。

local write の atomicity
-------------------------

``LocalFilesystemStore`` は次の手順で書きます。

#. target と同じ directory に一時 file を作る
#. UTF-8 byte を書き、file を ``fsync`` する
#. note 単位の lock を取得する
#. create なら hard link で「存在しない場合だけ」install する
#. update なら lock 内で version を再読し、一致後に ``os.replace`` する
#. 一時 file を削除する

update 時は既存 file の通常 permission bits（``0o777`` 部分）も一時 file へ引き継ぎます。読者からは
partial content ではなく、更新前または更新後のどちらかが見えます。

.. note::

   ここでいう atomicity は note file の置換単位です。directory entry の fsync までを
   含む crash durability は現在の契約に含みません。

POSIX writer lock
-----------------

``fcntl`` が利用できる POSIX 環境では、同じ note path に対する memoc writer を
advisory lock で直列化します。lock file は概念上、次の場所にあります。

.. code-block:: text

   <system-temp>/memoc-<uid>/locks/<hash-of-note-path>.lock

二 process が同じ expected version で同時に更新しても、一方が成功した後、他方は
lock 内の再確認で ``version_conflict`` になります。

.. warning::

   editor や shell command が underlying file を直接書く場合、その writer は advisory
   lock に参加しません。memoc 自身の write は partial になりませんが、外部 writer の
   書き方と完全な直列化は保証しません。``fcntl`` がない platform でも lock なしで動作します。

path safety
-----------

``repository``、``source_branch``、note ``path`` は slash 区切りの論理パスです。
次を拒否します。

* 空文字列（list の空 prefix だけは許可）
* 絶対パス
* 末尾 slash
* 空 segment、``.``、``..``
* backslash
* ASCII control character
* 解決後に ``memory_books_root`` の外へ出るパス
* note file 自体の symlink

Python API の例です。

.. code-block:: python

   from memory_core import InvalidNoteReferenceError, NoteRef

   invalid_paths = ["../secret.md", "/etc/passwd", "design//plan.md", "plan.md/"]

   for path in invalid_paths:
       try:
           NoteRef(
               repository="github.com/acme/widget",
               scope="share",
               path=path,
           )
       except InvalidNoteReferenceError as error:
           print(error.code, path)

note directory の symlink を含む解決結果も ``memory_books_root`` 内に留まる必要があります。
最終 note path が symlink の場合は、root 内を指していても拒否します。

text encoding
-------------

write の入力は Python ``str`` または CLI stdin の text で、UTF-8 として保存します。
read 対象が valid UTF-8 でなければ ``store_unavailable`` になります。

.. code-block:: console

   $ printf '日本語のメモ\n' | memoc write share japanese.md
   created japanese.md sha256:...
   $ memoc read share japanese.md --json
   {"content":"日本語のメモ\n","path":"japanese.md","repository":"github.com/acme/widget","scope":"share","size":19,"source_branch":null,"version":"sha256:..."}

``size`` は UTF-8 byte 数です。list は本文を decode せず byte から version と size を
計算するため、binary file が既に置かれている場合は list には現れても read は失敗します。

error taxonomy
--------------

.. list-table:: error code
   :header-rows: 1
   :widths: 30 35 35

   * - code
     - Python exception
     - 条件
   * - ``invalid_note_reference``
     - :class:`~memory_core.InvalidNoteReferenceError`
     - scope combination または論理パスが不正
   * - ``memory_collection_not_found``
     - :class:`~memory_core.MemoryCollectionNotFoundError`
     - ``share`` / branch collection が未初期化
   * - ``note_not_found``
     - :class:`~memory_core.NoteNotFoundError`
     - read/update 対象が存在しない
   * - ``note_already_exists``
     - :class:`~memory_core.NoteAlreadyExistsError`
     - create-only 対象が既に存在する
   * - ``version_conflict``
     - :class:`~memory_core.VersionConflictError`
     - expected version と actual version が不一致
   * - ``store_unavailable``
     - :class:`~memory_core.StoreUnavailableError`
     - I/O、permission、encoding、lock などの失敗
   * - ``store_error``
     - :class:`~memory_core.MemoryStoreError`
     - storage error の基底 code
   * - ``context_error``
     - ``ContextError``
     - manifest の形式、schema、repository が不正
   * - ``memoc_error``
     - ``MemocError`` / ``ConfigError``
     - CLI context、config、Git/ghq 解決などの失敗

``--json`` command の実行時エラーは、次の共通 envelope を stderr へ出します。

.. code-block:: json

   {
     "error": {
       "code": "note_not_found",
       "message": "note not found: /path/to/note.md"
     },
     "ok": false
   }

``version_conflict`` だけは追加で ``expected_version`` と ``actual_version`` を返します。
非 JSON mode では ``memoc: <message>`` という一行を stderr へ出します。
