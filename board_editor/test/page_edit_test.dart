import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as route;
import 'package:zy_board_editor/generated/board/Source.pb.dart' as src;

void main() {
  final input = File(
    '../reports/evidence/board/artwork-edit-base.zip',
  ).readAsBytesSync();
  BoardArchive open() => BoardArchive.open('art.zip', input);
  test('consecutive image edits round like sequential Android float matrices', () {
    final b = open(), page = b.current as BlackboardPage;
    PageArtwork image() => page.artwork.singleWhere((a) => a.image != null);
    expect(
      () => page.transformImage(image(), scale: 1e-50),
      throwsFormatException,
    );
    page.transformImage(
      image(),
      scale: 1.5,
      degrees: 90,
      move: const Offset(20, -12),
    );
    page.transformImage(image(), move: const Offset(0, 40.0000081));
    // The second delta rounds to 40.00000762939453 in its native matrix chunk.
    // Its sum with 111.75 is a float midpoint, rounded to even by the Android VM.
    expect(image().transform[5], 151.75);
    final restored = BoardArchive.open('again.zip', b.bytes());
    expect(
      restored.current.artwork.singleWhere((a) => a.image != null).transform[5],
      151.75,
    );
  });
  test(
    'image gestures preserve the source and rotate about its displayed centre',
    () {
      final b = open(), page = b.current as BlackboardPage;
      page.doc.cameraMatrix
        ..scaleX = 2
        ..scaleY = 2
        ..transX = 10
        ..transY = 20;
      page.refresh();
      final art = page.artwork.singleWhere((a) => a.image != null);
      expect(art.label, '图片 · tiles.png');
      expect(art.containsImagePoint(const Offset(995, 425)), true);
      expect(page.transformImage(art, degrees: 360), false);
      expect(() => page.transformImage(art, scale: 0), throwsFormatException);
      expect(
        () => page.transformImage(art, degrees: double.nan),
        throwsFormatException,
      );
      expect(b.changed, isEmpty);
      final source = b.read('lesson/p1/3_file.bin');
      final pixels = b.read('lesson/res/image/tiles.png');
      page.transformImage(
        art,
        scale: 1.5,
        degrees: 90,
        move: const Offset(30, -16),
      );
      final saved = BoardArchive.open('image.zip', b.bytes());
      final transformed = saved.current.artwork.singleWhere(
        (a) => a.image != null,
      );
      final m = transformed.transform;
      final expected = [0, -3, 1182.5, 3, 0, 251.5, 0, 0, 1];
      for (int i = 0; i < expected.length; i++) {
        expect(m[i], closeTo(expected[i], 0.0001));
      }
      expect(transformed.containsImagePoint(const Offset(1025, 409)), true);
      expect(transformed.containsImagePoint(const Offset(1200, 409)), false);
      expect(saved.read('lesson/p1/3_file.bin'), source);
      expect(saved.read('lesson/res/image/tiles.png'), pixels);
      final refs = route.RouterRecord.fromBuffer(
        saved.read('lesson/p1/router.bin'),
      );
      final cmdFile = cmd.CommandSource.fromBuffer(
        saved.read('lesson/p1/${refs.commandRecord.single.fileName}'),
      );
      final command = cmdFile.commandInfo.single;
      expect(command.commandEnum.value, 3);
      final record = cmd.CommandSource_CommandInfo_GraphMatrix.fromBuffer(
        command.data,
      );
      expect(record.graphData.single.graphId, 'image');
      expect(record.sourceFileName, refs.matrixSourceRecord.single.fileName);
      expect(() => page.transformImage(art), throwsStateError);
    },
  );
  test(
    'editing a source-only text preserves its native snapshot and original source',
    () {
      final b = BoardArchive.open(
        'sparse.zip',
        File('../reports/evidence/board/schema-artwork.zip').readAsBytesSync(),
      );
      final p = b.current as BlackboardPage;
      final text = p.artwork.first;
      final original = b.read('lesson/p1/1_text.bin');
      p.editArtwork(text, move: const Offset(1, 2));
      final saved = p.doc.graphSnapshot.childGraph.first;
      expect(saved.content, text.text);
      expect(saved.paint.textSize, 28);
      expect(b.read('lesson/p1/1_text.bin'), original);
      final refs = route.RouterRecord.fromBuffer(
        b.read('lesson/p1/router.bin'),
      );
      final records = cmd.CommandSource.fromBuffer(
        b.read('lesson/p1/${refs.commandRecord.single.fileName}'),
      ).commandInfo;
      expect(records.map((c) => c.commandEnum.value), [4, 3]);
      final delta = cmd.CommandSource_CommandInfo_GraphChange.fromBuffer(
        records.first.data,
      );
      expect(delta.content, text.text);
      expect(delta.paint.textSize, 28);
    },
  );
  test(
    'v6 artwork changes preserve history, resource hashes and native page-space matrices',
    () {
      final b = open(), p = b.current as BlackboardPage;
      final original = b.read('lesson/p1/1_text.bin');
      final title = p.artwork.first;
      expect(p.editArtwork(title, content: title.text), false);
      expect(b.bytes(), input);
      expect(
        p.editArtwork(
          title,
          content: 'Board 42',
          argb: 0xff164e91,
          size: 36,
          move: const Offset(32, 12),
        ),
        true,
      );
      expect(p.artwork.first.text, 'Board 42');
      expect(p.artwork.first.transform, [1, 0, 72, 0, 1, 47, 0, 0, 1]);
      final polygon = p.artwork.singleWhere((a) => a.id == 'triangle');
      expect(polygon.transform, [1, 0, 230, 0, 1, 150, 0, 0, 1]);
      expect(
        p.editArtwork(
          polygon,
          vertices: const [Offset(1, 2), Offset(30, 12), Offset(3, 8)],
          move: const Offset(7, -2),
        ),
        true,
      );
      final later = BoardArchive.open('again.zip', b.bytes()),
          restored = later.current as BlackboardPage;
      expect(later.read('lesson/p1/1_text.bin'), original);
      expect(restored.artwork.first.text, 'Board 42');
      expect(restored.artwork.first.style.textSize, 36);
      expect(
        restored.artwork.singleWhere((a) => a.id == 'triangle').transform,
        [1, 0, 237, 0, 1, 148, 0, 0, 1],
      );
      final refs = route.RouterRecord.fromBuffer(
        later.read('lesson/p1/router.bin'),
      );
      final kinds = <int>[];
      for (final r in [...refs.commandRecord, ...refs.matrixSourceRecord]) {
        final data = later.read('lesson/p1/${r.fileName}');
        expect(
          sha256
              .convert(data)
              .toString()
              .replaceFirst(RegExp('^0+'), '')
              .padLeft(32, '0'),
          r.validate,
        );
        if (r.fileName.endsWith('_command.bin')) {
          kinds.addAll(
            cmd.CommandSource.fromBuffer(
              data,
            ).commandInfo.map((c) => c.commandEnum.value),
          );
        }
      }
      expect(kinds, [4, 3, 12, 3]);
    },
  );
  test(
    'clearing source-backed text keeps the old resource and creates a replayable empty snapshot',
    () {
      final b = open(), p = b.current as BlackboardPage;
      expect(
        () => p.editArtwork(p.artwork.first, size: double.nan),
        throwsFormatException,
      );
      expect(b.bytes(), input);
      final previous = b.read('lesson/p1/1_text.bin');
      p.editArtwork(p.artwork.first, content: '');
      expect(p.artwork.first.text, '');
      final refs = route.RouterRecord.fromBuffer(
        b.read('lesson/p1/router.bin'),
      );
      expect(refs.textSourceRecord, hasLength(2));
      expect(b.read('lesson/p1/1_text.bin'), previous);
      final newSource = b.read(
        'lesson/p1/${refs.textSourceRecord.last.fileName}',
      );
      expect(src.TextSource.fromBuffer(newSource).textInfo.single.content, '');
      final command = cmd.CommandSource.fromBuffer(
        b.read('lesson/p1/${refs.commandRecord.last.fileName}'),
      ).commandInfo.single;
      expect(command.commandEnum.value, 12);
      final snap = cmd.CommandSource_CommandInfo_REBUILD.fromBuffer(
        command.data,
      );
      expect(
        snap.snapshot.childGraph.first.sourceFileName,
        refs.textSourceRecord.last.fileName,
      );
      expect(
        BoardArchive.open('again.zip', b.bytes()).current.artwork.first.text,
        '',
      );
    },
  );
}
