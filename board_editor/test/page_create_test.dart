import 'dart:io';
import 'dart:ui' show Rect, Size;
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as route;
import 'package:zy_board_editor/generated/board/Source.pb.dart' as src;
import 'package:crypto/crypto.dart';
import 'package:zy_board_editor/generated/board/PageRouter.pb.dart' as pages;

void main() {
  BoardArchive open(String name) => BoardArchive.open(
    name,
    File('../reports/evidence/board/$name').readAsBytesSync(),
  );
  test(
    'new and appended pages have distinct replay roots and survive both export modes',
    () {
      final note = BoardArchive.blankBlackboard();
      expect(note.entries, ['lesson/p1/snapshot.bin']);
      final first = note.current as BlackboardPage;
      first.createArtwork(
        ArtworkKind.text,
        area: const Rect.fromLTWH(10, 15, 170, 60),
        argb: 0xff123456,
        content: 'Page one',
        penSize: 25,
      );
      final root1 = first.doc.graphSnapshot.id;
      note.addBlackboardPage();
      expect(note.index, 1);
      final second = note.current as BlackboardPage;
      expect(second.doc.graphSnapshot.id, isNot(root1));
      expect(second.artwork, isEmpty);
      second.draw(
        Ink([const Offset(20, 20), const Offset(80, 70)], 0xff263238, 4),
      );
      for (final data in [note.bytes(), note.cloudNoteBytes()]) {
        final b = BoardArchive.open('export.zip', data);
        expect(b.entries, ['lesson/p1/snapshot.bin', 'lesson/p2/snapshot.bin']);
        final list = pages.PageRouter.fromBuffer(
          b.read('lesson/page_router.bin'),
        );
        expect(list.pageInfo.map((i) => i.pageIndex), [0, 1]);
        expect(b.current.artwork.single.text, 'Page one');
        expect(b.current.strokes, isEmpty);
        for (var j = 0; j < 2; j++) {
          b.select(j);
          final page = b.current as BlackboardPage;
          expect(page.strokes.length, j);
          expect(page.size, const Size(1200, 900));
          final path = 'lesson/p${j + 1}/';
          final refs = route.RouterRecord.fromBuffer(
            b.read('${path}router.bin'),
          );
          final action = cmd.CommandSource.fromBuffer(
            b.read(path + refs.commandRecord.first.fileName),
          ).commandInfo.single;
          final add = cmd.CommandSource_CommandInfo_GraphData.fromBuffer(
            action.data,
          );
          expect(action.commandEnum.value, 1);
          expect(add.parentGraphId, '');
          expect(add.graphId, page.doc.graphSnapshot.id);
          expect(add.outRect.right, greaterThan(3.4e38));
        }
      }
    },
  );
  const box = Rect.fromLTWH(30, 45, 80, 70);
  test(
    'a v6 empty page records new artwork in drawing order and restores the source and placement',
    () {
      final archive = open('schema-page.zip'),
          p = archive.current as BlackboardPage;
      for (final kind in [
        ArtworkKind.text,
        ArtworkKind.oval,
        ArtworkKind.rectangle,
        ArtworkKind.triangle,
      ]) {
        p.createArtwork(
          kind,
          area: box,
          argb: 0xff112233,
          content: '示例',
          penSize: 20,
        );
      }
      final reopened = BoardArchive.open('page.zip', archive.bytes()),
          page = reopened.current as BlackboardPage;
      expect(page.artwork.map((a) => a.id).toSet().length, 4);
      expect(page.artwork.first.text, '示例');
      expect(page.artwork[1].oval, true);
      expect(page.artwork[2].polygon!.length, 4);
      expect(page.artwork[3].polygon!.length, 3);
      final refs = route.RouterRecord.fromBuffer(
        reopened.read('lesson/p1/router.bin'),
      );
      expect(refs.commandRecord.length, 4);
      for (var i = 0; i < 4; i++) {
        final a = page.artwork[i],
            record = cmd.CommandSource.fromBuffer(
              reopened.read('lesson/p1/${refs.commandRecord[i].fileName}'),
            );
        expect(a.transform, [1, 0, 30, 0, 1, 45, 0, 0, 1]);
        expect(a.bounds, Offset.zero & box.size);
        expect(record.commandInfo.map((c) => c.commandEnum.value), [1, 3]);
        final add = cmd.CommandSource_CommandInfo_GraphData.fromBuffer(
          record.commandInfo.first.data,
        );
        expect(add.graphId, a.id);
        expect(add.parentGraphId, page.doc.graphSnapshot.id);
        expect(add.sourceId, 0);
        expect(reopened.has('lesson/p1/${add.sourceFileName}'), true);
      }
    },
  );
  test(
    'a picture uses content hashes, never replaces a sibling resource, and invalid inserts preserve every byte',
    () {
      final archive = open('artwork-edit-base.zip'),
          p = archive.current as BlackboardPage;
      final bytes = archive.read('lesson/res/image/tiles.png');
      final before = archive.bytes();
      for (final name in ['', '..']) {
        expect(
          () => p.createArtwork(
            ArtworkKind.image,
            area: box,
            argb: 0,
            imageName: name,
            imageBytes: bytes,
          ),
          throwsFormatException,
        );
        expect(archive.bytes(), before);
      }
      expect(
        () =>
            p.createArtwork(ArtworkKind.text, area: box, argb: 0, content: ' '),
        throwsFormatException,
      );
      expect(archive.bytes(), before);
      p.createArtwork(
        ArtworkKind.image,
        area: Offset.zero & const Size(32, 32),
        argb: 0,
        imageName: 'tiles.png',
        imageBytes: bytes,
      );
      final r = route.RouterRecord.fromBuffer(
        archive.read('lesson/p1/router.bin'),
      );
      final f = src.FileSource.fromBuffer(
        archive.read('lesson/p1/${r.fileSourceRecord.last.fileName}'),
      ).fileInfo.single;
      expect(f.name, 'tiles-2.png');
      expect(f.width, 32);
      expect(f.height, 32);
      expect(
        f.validate,
        sha256
            .convert(bytes)
            .toString()
            .replaceFirst(RegExp('^0+'), '')
            .padLeft(32, '0'),
      );
      expect(archive.read('lesson/res/image/tiles.png'), bytes);
      expect(archive.read('lesson/res/image/tiles-2.png'), bytes);
      expect(p.artwork.last.image, bytes);
      expect(
        cmd.CommandSource.fromBuffer(
          archive.read('lesson/p1/${r.commandRecord.last.fileName}'),
        ).commandInfo.length,
        1,
      );
    },
  );
}
