import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/utils/Paint.pb.dart' as wire;

void main() {
  test(
    'live path compensates for the camera radius and tolerates a collapsed camera in source data',
    () {
      final brush = wire.Paint(width: 24);
      expect(
        PageCursor(Offset.zero, [
          1.5,
          0,
          0,
          0,
          .75,
          0,
          0,
          0,
          1,
        ], brush).localRadius,
        closeTo(11.3137085, .000001),
      );
      expect(
        PageCursor(Offset.zero, [0, 0, 1, 0, 1, 0, 0, 0, 1], brush).localRadius,
        12,
      );
    },
  );
  final input = File(
    '../reports/evidence/board/cursor/native.zip',
  ).readAsBytesSync();
  BoardArchive original() => BoardArchive.open('native.zip', input);

  test(
    'native finger and pen are transient, preserve their widths under zoom and rewind independently of ink',
    () {
      final p = original().current as BlackboardPage;
      final replay = p.replay;
      expect(replay.available, isTrue);
      for (final (ms, x, y, diameter) in [
        (850, 160, 120, 26),
        (970, 225, 145, 26),
        (1095, 265, 180, 26),
        (1450, 340, 170, 14),
        (1560, 380, 194, 14),
        (1670, 404, 228, 14),
        (970, 225, 145, 26),
      ]) {
        final frame = replay.seek(ms);
        expect(frame.strokes, hasLength(1));
        final dot = frame.cursor!;
        expect(
          (dot.center - Offset(x.toDouble(), y.toDouble())).distance,
          lessThan(.0001),
        );
        expect(dot.localRadius * 1.25 * 2, closeTo(diameter, .0001));
      }
      for (final ms in [700, 1156, 1414, 1764, 2011]) {
        expect(replay.seek(ms).cursor, isNull);
      }
      expect(p.strokes, hasLength(1));
    },
  );

  test(
    'append writes a timed gesture without changing the snapshot, preview or original resources',
    () {
      final book = original(), p = book.current as BlackboardPage;
      p.appendCursor(
        [const Offset(80, 150), const Offset(110, 170), const Offset(160, 120)],
        [100, 200, 350],
        0xff228855,
        18,
      );
      expect(
        book.changed.keys.where(
          (name) =>
              name.endsWith('snapshot.bin') || name.endsWith('screenshot.png'),
        ),
        isEmpty,
      );
      expect(book.pendingPreviews, isEmpty);
      expect(p.pageAudio.durationMs, 2325);
      expect(p.replay.seek(1450).cursor!.brush.width, 14);
      expect(p.replay.seek(2150).cursor!.center.dx, closeTo(110, .0001));
      expect(p.replay.seek(2261).cursor, isNull);
      final restored =
          BoardArchive.open('cursor.zip', book.bytes()).current
              as BlackboardPage;
      expect(restored.strokes, hasLength(1));
      final frame = restored.replay.seek(2150);
      expect(frame.strokes, hasLength(1));
      expect(frame.cursor!.brush.color.toUnsigned(32), 0xff228855);
    },
  );

  test(
    'first recording can start on a blank page and is confined to that page',
    () {
      final book = BoardArchive.blankBlackboard();
      book.addBlackboardPage();
      final p = book.current as BlackboardPage;
      expect(p.canRecordCursor, isTrue);
      final before = book.bytes();
      expect(
        () => p.appendCursor([Offset.zero, const Offset(1, 1)], [85, 4], -1, 6),
        throwsFormatException,
      );
      expect(book.bytes(), before);
      p.appendCursor([Offset.zero, const Offset(1, 1)], [80, 80], -1, 6);
      final out = book.bytes();
      final empty = BoardArchive.open('two.zip', out).current as BlackboardPage;
      expect(empty.pageAudio.durationMs, 0);
      final page2 =
          BoardArchive.open('two.zip', out, pageIndex: 1).current
              as BlackboardPage;
      expect(page2.pageAudio.durationMs, 65);
      expect(page2.replay.seek(0).cursor!.center, const Offset(1, 1));
      expect(page2.replay.seek(1).cursor, isNull);
    },
  );
}
