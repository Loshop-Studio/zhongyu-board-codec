import 'dart:io';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:fixnum/fixnum.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/Header.pb.dart' as hdr;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as route;

void main() {
  final original = File(
    '../reports/evidence/board/page-audio.zip',
  ).readAsBytesSync();
  BoardArchive open() => BoardArchive.open('lesson.zip', original);
  const routerPath = 'lesson/p1/router.bin';
  route.RouterRecord refs(BoardArchive a) =>
      route.RouterRecord.fromBuffer(a.read(routerPath));
  String signature(List<int> bytes) => sha256
      .convert(bytes)
      .toString()
      .replaceFirst(RegExp('^0+'), '')
      .padLeft(32, '0');

  test(
    'V6 playback uses outer command times, both silence bounds and the local page header',
    () {
      final note = open();
      final page = note.current as BlackboardPage;
      final track = page.pageAudio;
      expect(track.issue, isNull);
      expect(track.durationMs, 2800);
      expect(track.clips.map((c) => [c.filename, c.startMs, c.endMs]), [
        ['first.wav', 200, 1400],
        ['second.wav', 1800, 2600],
      ]);
      expect(
        [
          0,
          199,
          200,
          1399,
          1400,
          1799,
          1800,
          2599,
          2600,
          2799,
        ].map((i) => track.clipAt(i)?.filename),
        [
          null,
          null,
          'first.wav',
          'first.wav',
          null,
          null,
          'second.wav',
          'second.wav',
          null,
          null,
        ],
      );
      expect(page.audioBytes('first.wav')!.take(4), [82, 73, 70, 70]);
      expect(page.audioBytes('missing.wav'), isNull);
      note.select(1);
      expect((note.current as BlackboardPage).pageAudio.clips, isEmpty);
      expect(note.bytes(), original);
    },
  );
  test(
    'appends after trailing silence, preserves older messages and resolves media collisions',
    () {
      final note = open(), page = note.current as BlackboardPage;
      final first = page.audioBytes('first.wav')!;
      final shard = 'lesson/p1/${refs(note).audioRecord.single.fileName}';
      final old = cmd.CommandSource.fromBuffer(note.read(shard));
      final originalMembers = {
        for (final f in note.arch.files)
          if (f.isFile) f.name: note.read(f.name),
      };
      expect(
        page.appendAudio('first.wav', first, 1200, gapMs: 100),
        'first-2.wav',
      );
      for (final bytes in [note.bytes(), note.cloudNoteBytes()]) {
        final result = BoardArchive.open('again.zip', bytes),
            p = result.current as BlackboardPage;
        expect(p.pageAudio.durationMs, 4100);
        expect(p.pageAudio.clips.last.startMs, 2900);
        expect(p.audioBytes('first-2.wav'), first);
        expect(
          hdr.Header.fromBuffer(
            result.read('lesson/p1/header.bin'),
          ).duration.toInt(),
          4100,
        );
        for (final f in originalMembers.entries) {
          if (![routerPath, 'lesson/p1/header.bin', shard].contains(f.key))
            expect(result.read(f.key), f.value, reason: f.key);
        }
        final chunk = result.read(shard),
            rows = cmd.CommandSource.fromBuffer(chunk).commandInfo;
        expect(refs(result).audioRecord.single.validate, signature(chunk));
        for (var i = 0; i < 2; i++)
          expect(rows[i].writeToBuffer(), old.commandInfo[i].writeToBuffer());
        expect(rows.last.delayTime.toInt(), 300);
        expect(rows.last.duration.toInt(), 1200);
        expect(rows.last.isPlay, isTrue);
        final data = cmd.CommandSource_CommandInfo_AudioStart.fromBuffer(
          rows.last.data,
        );
        expect([data.fileName, data.duration.toInt()], ['first-2.wav', 1200]);
      }
    },
  );
  test(
    'delayed commands gate later overlapping clips and outer durations control the seek window',
    () {
      final note = open();
      final path = 'lesson/p1/${refs(note).audioRecord.single.fileName}';
      final shard = cmd.CommandSource.fromBuffer(note.read(path));
      shard.commandInfo[1]
        ..delayTime = Int64(-1300)
        ..duration = Int64(500);
      note.changed[path] = shard.writeToBuffer();
      final page =
          BoardArchive.open('overlap.zip', note.bytes()).current
              as BlackboardPage;
      expect(page.pageAudio.clipAt(170), isNull);
      expect(page.pageAudio.clipAt(200)?.filename, 'second.wav');
      expect(page.pageAudio.clipAt(599)?.filename, 'second.wav');
      expect(page.pageAudio.clipAt(600)?.filename, 'first.wav');
      expect(page.pageAudio.clipAt(1400), isNull);
    },
  );

  test(
    'version-only page headers preserve zero duration and older short headers carry their duration into an audio edit',
    () {
      final empty = open();
      empty.changed['lesson/p1/header.bin'] = Uint8List.fromList([8, 6]);
      final zero = BoardArchive.open('version.zip', empty.cloudNoteBytes());
      expect((zero.current as BlackboardPage).pageAudio.durationMs, 0);
      empty.changed['lesson/p1/header.bin'] = Uint8List.fromList([8, 100]);
      final legacy = BoardArchive.open('short.zip', empty.bytes());
      final page = legacy.current as BlackboardPage;
      expect(page.pageAudio.durationMs, 100);
      page.appendAudio('third.wav', page.audioBytes('second.wav')!, 800);
      final header = hdr.Header.fromBuffer(legacy.read('lesson/p1/header.bin'));
      expect(
        [header.version, header.width, header.duration.toInt()],
        [6, 1200, 3400],
      );
    },
  );

  test(
    'a full shard rolls over and a missing shard stops append without changing the archive',
    () {
      final note = open(), ref = refs(note).audioRecord.single;
      final path = 'lesson/p1/${ref.fileName}',
          full = cmd.CommandSource.fromBuffer(note.read(path));
      while (full.commandInfo.length < 100) {
        full.commandInfo.add(cmd.CommandSource_CommandInfo());
      }
      note.changed[path] = full.writeToBuffer();
      final before = note.bytes();
      final loaded = BoardArchive.open('full.zip', before),
          p = loaded.current as BlackboardPage;
      p.appendAudio('third.wav', p.audioBytes('second.wav')!, 800);
      expect(refs(loaded).audioRecord.length, 2);
      expect(loaded.read(path), note.read(path));
      expect(p.pageAudio.clips.last.startMs, 2800);
      final broken = refs(note)
        ..audioRecord.add(
          route.RouterRecord_SourceCommandRecord(fileName: 'absent.bin'),
        );
      note.changed[routerPath] = broken.writeToBuffer();
      final damaged = note.bytes(),
          inspected = BoardArchive.open('missing.zip', damaged);
      final incomplete = inspected.current as BlackboardPage;
      expect(incomplete.pageAudio.issue, contains('absent.bin'));
      expect(
        () => incomplete.appendAudio('no.wav', Uint8List(1), 10),
        throwsFormatException,
      );
      expect(inspected.bytes(), damaged);
    },
  );
}
