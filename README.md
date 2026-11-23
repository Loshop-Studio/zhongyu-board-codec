# Zhongyu board formats and Flutter editor

Open a local Cloud Note MDB, BIN, note ZIP or unpacked notebook directory and edit its supported content in the browser. The Dart codecs support SimpleBoard, Sketch V1–V5 and page-based Blackboard notes. Fixtures and original Android readback evidence accompany the [format and storage report](reports/画板与存储.md).

## Download the editor

The prebuilt editor opens supported Cloud Note MDB, BIN, and note ZIP files. Download the latest [flutter-web.zip](https://github.com/Loshop-Studio/zhongyu-board-codec/releases/latest/download/flutter-web.zip). Extract it into a directory and run `python3 -m http.server 8765 --bind 127.0.0.1` in that directory. Open [the editor](http://127.0.0.1:8765) in the browser.

## Run the editor

From the repository root, use Flutter with the Dart SDK range in [pubspec.yaml](board_editor/pubspec.yaml).

```sh
cd board_editor
flutter pub get
flutter test
flutter build web --release --no-web-resources-cdn
python3 -m http.server 8765 --bind 127.0.0.1 --directory build/web
```

Open [the local editor](http://127.0.0.1:8765) and select **打开笔记**. Try the [Sketch V5 sample](reports/evidence/board/sketch-shapes/web.bin), [V1 notebook](reports/evidence/board/sketch-shapes/v1-web.zip) or [native Blackboard V6 notebook](reports/evidence/board/native-v6-recording.zip).

## Edit Cloud Note handwriting

Choose **打开笔记** and select a closed Cloud Note 1.13.5 `data.mdb`, a renamed MDB, or a notebook ZIP. Use the folder button for an unpacked notebook. The [two-page native fixture](reports/evidence/board/page_mdb/native-v6-two-pages.mdb) opens with three strokes on its first page.

Click a stroke or select it from the stroke list. Choose a color or line width, use **调整采样点** to drag a point inside the original stroke bounds, or select **平滑笔迹** to smooth its interior points. Undo and redo apply across page switches. **导出 MDB** downloads the selected database. **导出 ZIP** retains the folder layout, companion files and edits to any opened stores.

The handwriting view restores a usable page snapshot and resumes pending commands from the page’s saved chunk and index. Without a usable snapshot, it replays the stored graph commands against the ObjectBox sources. Stroke edits update existing paint and coordinate fields in the exported copy. Object IDs, relation keys and timestamps are preserved. Companion BINs and preview images retain their original bytes. The editor preserves non-ink objects in the database and shows its text in **数据库详情**.

The original Android 11 reader reopened the [edited MDB](reports/evidence/board/mdb-ink/edited.mdb) and returned the new paint and sample coordinates. The [comparison](reports/evidence/board/mdb-ink/comparison.json) records the four changed scalar fields and the unchanged entity and relation counts. [Before](reports/evidence/board/mdb-ink/before.png) · [After](reports/evidence/board/mdb-ink/after.png)

## Source and evidence

- [Flutter source and generated Protobuf bindings](board_editor/lib/)
- [Flutter regression tests](board_editor/test/)
- [Fixtures, browser exports and native comparisons](reports/evidence/board/)
- [Android readback evidence](reports/evidence/art/)
- [Browser and Android verification tools](tools/verification/)

Flutter tests use the files in this repository. The optional Android comparison probes load original APKs from `中育apk/` and use a disposable emulator. Input APKs and the corresponding build projects are available from the [Zhongyu repository](https://github.com/Loshop-Studio/zhongyu-android-reverse) and the [Linspirer repository](https://github.com/Loshop-Studio/linspirer-android-reverse).
