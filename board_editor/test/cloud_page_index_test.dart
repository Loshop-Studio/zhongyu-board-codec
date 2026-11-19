import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  final sample = File(
    '../reports/evidence/board/cloud-index/native.zip',
  ).readAsBytesSync();
  final sketch = File(
    '../reports/evidence/board/art-actions.bin',
  ).readAsBytesSync();
  Uint8List data(Object value) =>
      Uint8List.fromList(utf8.encode(jsonEncode(value)));
  test(
    'opens the Android index in order including both occurrences of a page',
    () {
      final board = BoardArchive.open('native.zip', sample);
      expect(board.entries, [
        '课堂本/第2页/actions.bin',
        '课堂本/第一页/actions.bin',
        '课堂本/第2页/actions.bin',
      ]);
      expect(board.current.strokes.length, 2);
      board.select(1);
      expect(board.current.strokes.length, 1);
      expect(board.bytes(), sample);
    },
  );
  test(
    'indexes are local to the notebook and nested duplicate names keep their identity',
    () {
      final board = BoardArchive.fromDirectory('fixture', {
        'album/index.json': data([
          '/tablet/book/unit/b',
          '/tablet/book/unit/a',
        ]),
        'album/unit/a/actions.bin': sketch,
        'album/unit/b/actions.bin': sketch,
        'album/b/actions.bin': sketch,
        'album/unlisted/actions.bin': sketch,
        'album/inner/index.json': data(['/else/c']),
        'album/inner/c/actions.bin': sketch,
        'album/inner/d/actions.bin': sketch,
        'sibling/actions.bin': sketch,
      });
      expect(board.entries, [
        'album/unit/b/actions.bin',
        'album/unit/a/actions.bin',
        'album/inner/c/actions.bin',
        'sibling/actions.bin',
      ]);
    },
  );
  test(
    'empty native indexes hide unlisted pages and unrelated JSON does not claim them',
    () {
      final board = BoardArchive.fromDirectory('fixture', {
        'empty/index.json': data([]),
        'missing/index.json': data(['/old/gone']),
        'missing/unlisted/actions.bin': sketch,
        'empty/a/actions.bin': sketch,
        'other/index.json': data({'label': 'chapter'}),
        'other/b/actions.bin': sketch,
        'unrelated/index.json': data(['unrelated/metadata']),
        'unrelated/c/actions.bin': sketch,
      });
      expect(board.entries, ['other/b/actions.bin', 'unrelated/c/actions.bin']);
    },
  );
  test(
    'resource paths resolve identical suffixes from two former Android locations',
    () {
      final board = BoardArchive.fromDirectory('fixture', {
        'index.json': data(['/old/a', '/new/a', '/new/a']),
        'res.json': data([
          {'local': '/new/a/actions.bin', 'service': 'offline-fixture'},
        ]),
        'a/actions.bin': sketch,
      });
      expect(board.entries, ['a/actions.bin', 'a/actions.bin']);
    },
  );
  test(
    'inconsistent Android roots that equally explain a page are reported',
    () {
      expect(
        () => BoardArchive.fromDirectory('fixture', {
          'index.json': data(['/one/a', '/two/a']),
          'a/actions.bin': sketch,
        }),
        throwsFormatException,
      );
    },
  );
}
