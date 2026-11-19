import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Offset, Size;
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Header.pb.dart' as hdr;
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as route;
import 'package:zy_board_editor/generated/board/Source.pb.dart' as src;

void main() {
  final bytes = File(
    '../reports/evidence/board/native-v6-recording.zip',
  ).readAsBytesSync();
  BoardArchive open() => BoardArchive.open('native.zip', bytes);

  test(
    'scrolling thumbnail uses page coordinates and the native stroke margin',
    () {
      final input = File(
        '../reports/evidence/board/page-previews/native-scroll.zip',
      ).readAsBytesSync();
      final page =
          BoardArchive.open('scroll.zip', input).current as BlackboardPage;
      expect(page.camera[5], -576);
      expect(page.previewHeader.moveConfig.maxWidthTimes, 2);
      expect(page.strokes.last.points.first.dy, 220);
      page.refresh(applyCamera: false);
      expect(page.strokes.last.points.first.dy, 796);
      expect(page.contentBottom, 837);
      expect(page.camera[5], -576);
      page.refresh();
      expect(page.strokes.last.points.first.dy, 220);
    },
  );

  test(
    'an in-flight export freezes all edited pages and their thumbnails',
    () async {
      final book = open(), first = book.current as BlackboardPage;
      final ink = Ink(
        [const Offset(30, 60), const Offset(80, 120)],
        0xff19304a,
        4,
      );
      first.draw(ink);
      book.addBlackboardPage();
      final second = book.current as BlackboardPage;
      final gate = Completer<void>();
      final called = <String>[];
      final saving = book.export(
        cloudCopy: true,
        renderPreview: (page) async {
          called.add(page.name);
          await gate.future;
          return Uint8List.fromList([page.strokes.length]);
        },
      );
      second.draw(ink);
      book.commit();
      gate.complete();
      final result = await saving;
      expect(result.skipped, isEmpty);
      final copy = BoardArchive.open('saved.zip', result.bytes);
      expect(called, [first.name, second.name]);
      expect(copy.read('${first.dir}screenshot.png'), [3]);
      expect(copy.read('${second.dir}screenshot.png'), [0]);
      copy.select(1);
      expect(copy.current.strokes, isEmpty);
      expect(second.strokes, hasLength(1));
    },
  );

  test(
    'untouched exports return the original and a failed preview retains its source',
    () async {
      final book = open(), page = book.current as BlackboardPage;
      Future<Uint8List> fail(BlackboardPage _) async =>
          throw const FormatException('unknown object');
      final original = await book.export(cloudCopy: false, renderPreview: fail);
      expect(original.bytes, bytes);
      expect(original.skipped, isEmpty);
      page.draw(Ink([const Offset(6, 8), const Offset(32, 20)], 0xff223344, 3));
      final edited = await book.export(cloudCopy: false, renderPreview: fail);
      expect(edited.skipped.single, contains(page.name));
      final saved = BoardArchive.open('edited.zip', edited.bytes);
      final png = '${page.dir}screenshot.png';
      expect(saved.read(png), book.read(png));
      expect(saved.current.strokes, hasLength(3));
    },
  );

  test(
    'original recorder output with only page-level headers plays and remains byte-reversible',
    () {
      final book = open(), page = book.current as BlackboardPage;
      expect(book.has('header.bin'), false);
      expect(page.size, const Size(640, 480));
      expect(
        page.supportsArtworkEditing &&
            book.canAddBlackboardPage &&
            book.canExportCloudNote,
        true,
      );
      expect(page.pageAudio.clips, isEmpty);
      expect(page.pageAudio.durationMs, 1149);
      expect(page.strokes.map((s) => s.points.length), [5, 4]);
      expect(page.replay.seek(120).strokes, isEmpty);
      final first = page.replay.seek(390).strokes.single;
      expect(first.unfinishedPath, true);
      expect(first.points.length, 3);
      expect(page.replay.seek(600).strokes.length, 1);
      expect(page.replay.seek(900).strokes.length, 2);
      expect(page.replay.seek(1149).strokes.map((s) => s.points.length), [
        5,
        4,
      ]);
      expect(book.bytes(), bytes);
    },
  );

  test(
    'editing keeps measured touch intervals without extending the classroom timeline',
    () {
      final book = open(), page = book.current as BlackboardPage;
      const times = [1700000000000, 1700000000021, 1700000000147];
      page.draw(
        Ink(
          [const Offset(12, 15), const Offset(40, 45), const Offset(70, 65)],
          0xff112233,
          5,
          eventTimes: times,
        ),
      );
      final refs = route.RouterRecord.fromBuffer(
        book.read('${page.dir}router.bin'),
      );
      final command = cmd.CommandSource.fromBuffer(
        book.read(page.dir + refs.commandRecord.last.fileName),
      ).commandInfo.single;
      final points = src.TouchSource.fromBuffer(
        book.read(page.dir + refs.touchSourceRecord.last.fileName),
      ).touchInfo.single.touchEvent;
      expect(command.isPlay, false);
      expect(command.duration.toInt(), 147);
      expect(points.map((p) => p.eventTime.toInt()), times);
      expect(
        points.every(
          (p) => p.pointerCoords.isEmpty && p.pointerProperties.isEmpty,
        ),
        true,
      );
      expect(page.replay.seek(1148).strokes.length, 2);
      expect(page.replay.seek(1149).strokes.length, 3);
      expect(page.pageAudio.durationMs, 1149);
    },
  );

  test(
    'another page inherits geometry without creating a nonexistent notebook header',
    () {
      final book = open(), first = book.entries.single;
      book.addBlackboardPage();
      expect(book.has('header.bin'), false);
      final second = book.current as BlackboardPage;
      expect(second.size, const Size(640, 480));
      expect(second.pageAudio.durationMs, 0);
      expect(second.strokes, isEmpty);
      final copy = BoardArchive.open('copy.zip', book.cloudNoteBytes());
      expect(copy.entries, [first, 'p2/snapshot.bin']);
      expect((copy.current as BlackboardPage).pageAudio.durationMs, 1149);
      expect(copy.has('header.bin'), false);
      copy.select(1);
      expect((copy.current as BlackboardPage).supportsArtworkEditing, true);
    },
  );

  test(
    'partial or ambiguous headers allow inspecting the snapshot without assigning V6 editing',
    () {
      final book = open();
      final member = (book.current as BlackboardPage).dir + 'header.bin';
      final files = {
        for (final f in book.arch.files)
          if (f.isFile && f.name != member) f.name: f.readBytes()!,
      };
      files[member] = Uint8List.fromList([8, 6]);
      final partial = BoardArchive.fromDirectory('partial', files);
      expect((partial.current as BlackboardPage).supportsArtworkEditing, false);
      expect(partial.current.size, const Size(1200, 900));
      expect(partial.canExportCloudNote, false);
      files[member] = hdr.Header(
        version: 5,
        width: 640,
        height: 480,
      ).writeToBuffer();
      final older = BoardArchive.fromDirectory('older', files);
      expect((older.current as BlackboardPage).supportsArtworkEditing, false);
    },
  );
}
