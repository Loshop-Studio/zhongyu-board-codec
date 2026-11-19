import 'dart:convert';
import 'dart:io';
import 'dart:ui' show Size;
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as router;
import 'package:zy_board_editor/generated/board/Source.pb.dart' as src;

void main() {
  const dir = '../reports/evidence/board';
  final bytes = File('$dir/page-replay.zip').readAsBytesSync();
  BoardArchive open() => BoardArchive.open('page-replay.zip', bytes);

  test(
    'all original CommandThread seek checkpoints match in both directions',
    () {
      final archive = open(), page = archive.current as BlackboardPage;
      final trace = jsonDecode(
        File('$dir/page-replay-native.json').readAsStringSync(),
      );
      expect(page.replay.available, true);
      for (final row in trace['seek']) {
        final time = row['ms'] as int;
        final frame = page.replay.seek(time);
        final ids = List.from(row['graph_ids']), end = row['active_path_end'];
        final pending = end[0] >= 0;
        expect(
          frame.strokes.length,
          (ids.contains('ink') ? 1 : 0) + (pending ? 1 : 0),
          reason: 'stroke count at $time',
        );
        if (pending) {
          final stroke = frame.strokes.last, n = stroke.points.length;
          expect(stroke.unfinishedPath, true);
          expect(
            (stroke.points[n - 2] + stroke.points.last) / 2,
            Offset(end[0].toDouble(), end[1].toDouble()),
            reason: 'transient path endpoint at $time',
          );
        } else if (ids.contains('ink')) {
          expect(
            frame.strokes.first.points.first.dx,
            100 + row['ink_dx'],
            reason: 'matrix at $time',
          );
        }
        expect(
          frame.artwork.map((a) => a.text).toList(),
          ids.contains('title') ? [row['text']] : [],
          reason: 'text at $time',
        );
      }
      for (final row in trace['forward']) {
        final frame = page.replay.seek(row['ms'], direct: false);
        expect(frame.artwork.firstOrNull?.text ?? '', row['text']);
      }
      expect(page.strokes.single.points.first, const Offset(180, 140));
      expect(page.artwork.single.text, 'After');
      expect(archive.bytes(), bytes);
    },
  );

  test(
    'editing invalidates cached playback, stores a stroked path, and appends after the last recorded command',
    () {
      final archive = open(), page = archive.current as BlackboardPage;
      final earlier = page.replay;
      earlier.seek(1300);
      page.draw(
        Ink(
          [const Offset(30, 35), const Offset(55, 90), const Offset(85, 42)],
          0xff223344,
          6,
        ),
      );
      expect(identical(earlier, page.replay), false);
      final saved = BoardArchive.open('return.zip', archive.bytes()),
          current = saved.current as BlackboardPage;
      final refs = router.RouterRecord.fromBuffer(
        saved.read('lesson/p1/router.bin'),
      );
      final chunk = src.TouchSource.fromBuffer(
        saved.read('lesson/p1/${refs.touchSourceRecord.last.fileName}'),
      );
      expect(chunk.touchInfo.single.paint.style, 1);
      expect(current.replay.seek(1300).strokes, isEmpty);
      expect(current.replay.seek(3100).strokes.length, 2);
      expect(current.pageAudio.clips.length, 2);
      saved.select(1);
      expect((saved.current as BlackboardPage).replay.available, false);
    },
  );

  test(
    'missing recording command files leave the original notebook editable',
    () {
      final archive = open();
      final refs = router.RouterRecord.fromBuffer(
        archive.read('lesson/p1/router.bin'),
      );
      refs.commandRecord[0].fileName = 'missing.bin';
      archive.changed['lesson/p1/router.bin'] = refs.writeToBuffer();
      final reopened = BoardArchive.open('incomplete.zip', archive.bytes());
      final page = reopened.current as BlackboardPage;
      expect(page.replay.available, false);
      expect(page.replay.issue, contains('missing.bin'));
      expect(page.strokes, isNotEmpty);
      expect(page.pageAudio.clips.length, 2);
    },
  );

  test('each page uses its own recorded viewport', () {
    final note = open();
    expect(note.current.size, const Size(640, 480));
    note.select(1);
    expect(note.current.size, const Size(1200, 900));
  });

  test('a timed visual recording is available without audio', () {
    final archive = open();
    final refs = router.RouterRecord.fromBuffer(
      archive.read('lesson/p1/router.bin'),
    )..audioRecord.clear();
    archive.changed['lesson/p1/router.bin'] = refs.writeToBuffer();
    final page =
        BoardArchive.open('silent.zip', archive.bytes()).current
            as BlackboardPage;
    expect(page.pageAudio.clips, isEmpty);
    expect(page.replay.available, true);
    expect(page.replay.seek(700).strokes.single.unfinishedPath, true);
    expect(page.replay.seek(1300).strokes, isEmpty);
  });

  test('a missing opening graph stays in snapshot mode', () {
    final archive = open(),
        refs = router.RouterRecord.fromBuffer(
          archive.read('lesson/p1/router.bin'),
        );
    final path = 'lesson/p1/${refs.commandRecord.first.fileName}';
    final chunk = cmd.CommandSource.fromBuffer(archive.read(path))
      ..commandInfo.removeAt(0);
    archive.changed[path] = chunk.writeToBuffer();
    final page =
        BoardArchive.open('partial.zip', archive.bytes()).current
            as BlackboardPage;
    expect(page.replay.available, false);
    expect(page.replay.issue, contains('起始图元'));
  });
}
