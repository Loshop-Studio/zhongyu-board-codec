import 'dart:io';
import 'dart:typed_data';
import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  test(
    'a folder containing three native board families retains all files and can switch pages',
    () {
      final root = Directory('../reports/evidence/board');
      final members = <String, Uint8List>{};
      void addZip(String entry, String prefix) {
        final zip = ZipDecoder().decodeBytes(
          File('${root.path}/$entry').readAsBytesSync(),
        );
        for (final file in zip.files.where((f) => f.isFile)) {
          members['$prefix/${file.name}'] = file.readBytes()!;
        }
      }

      addZip('native-note-bundle.zip', 'note');
      addZip('native-simple-page.zip', 'draft');
      members['sketch/actions.bin'] = File(
        '${root.path}/art-actions.bin',
      ).readAsBytesSync();
      members['blank/remote_draft.bin'] = Uint8List(0);
      final bundle = BoardArchive.fromDirectory('原始目录', members);
      expect(bundle.name, '原始目录.zip');
      expect(bundle.entries, hasLength(4));
      expect(bundle.current.format, BoardFormat.pageSnapshot);
      final simple = bundle.entries.indexWhere((p) => p.startsWith('draft/'));
      bundle.select(simple);
      expect(bundle.current.format, BoardFormat.simple);
      expect(bundle.backgroundImage, isNotNull);
      bundle.select(bundle.entries.indexOf('sketch/actions.bin'));
      expect(bundle.current.format, BoardFormat.sketch);
      bundle.select(bundle.entries.indexOf('blank/remote_draft.bin'));
      expect(bundle.current.strokes, isEmpty);
      final first = bundle.bytes();
      expect(identical(first, bundle.bytes()), isTrue);
      final packed = ZipDecoder().decodeBytes(first);
      for (final e in members.entries) {
        expect(packed.findFile(e.key)!.readBytes(), e.value, reason: e.key);
      }
      expect(BoardArchive.open(bundle.name, first).entries, bundle.entries);
    },
  );
}
