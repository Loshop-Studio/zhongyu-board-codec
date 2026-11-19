import 'dart:io';
import 'dart:convert';
import 'package:archive/archive.dart';
import 'package:zy_board_editor/generated/board/Header.pb.dart' as header;
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:protobuf/well_known_types/google/protobuf/any.pb.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/sketch/DrawBoard.pb.dart' as sk;

Uint8List fixture(String path) =>
    File('../reports/evidence/board/$path').readAsBytesSync();
Ink stroke({PenShape shape = PenShape.free}) => Ink(
  [const Offset(14, 22), const Offset(65, 42)],
  0xff123456,
  4,
  shape: shape,
);

void main() {
  test('native simple sample, unknown fields and an empty draft', () {
    final bytes = Uint8List.fromList([
      ...fixture('art-simple.bin'),
      0xf8,
      0x07,
      0x43,
    ]);
    final doc = BoardFile.open('draft.bin', bytes);
    expect(doc.bytes(), bytes);
    expect(doc.strokes, hasLength(1));
    doc.draw(stroke());
    final updated = BoardFile.open('draft.bin', doc.bytes());
    expect(updated.strokes, hasLength(2));
    expect(updated.strokes.last.points.last, const Offset(65, 42));
    expect(updated.message.unknownFields.hasField(127), isTrue);
    final empty = BoardFile.open('remote_draft.bin', Uint8List(0));
    expect(empty.strokes, isEmpty);
    empty.draw(stroke());
    expect(
      BoardFile.open('remote_draft.bin', empty.bytes()).strokes,
      hasLength(1),
    );
    expect(
      () => BoardFile.open('header.bin', Uint8List(0)),
      throwsFormatException,
    );
  });
  test(
    'resolves ordered Blackboard text, geometry and images from page resources',
    () {
      final archive = BoardArchive.open(
        'rich.zip',
        fixture('schema-artwork.zip'),
      );
      final page = archive.current as BlackboardPage;
      expect(page.unrendered, isEmpty);
      expect(page.artwork, hasLength(4));
      expect(page.artwork[0].text, contains('Blackboard'));
      expect(page.artwork[1].oval, isTrue);
      expect(page.artwork[2].polygon, hasLength(3));
      expect(page.artwork[3].image!.sublist(0, 4), [137, 80, 78, 71]);
      page.draw(stroke());
      final updated =
          BoardArchive.open('rich.zip', archive.bytes()).current
              as BlackboardPage;
      expect(updated.artwork[3].beforeStroke, 0);
      expect(updated.strokes, hasLength(1));
    },
  );
  test(
    'Cloud Note copy uses page BINs and does not mutate the complete backup',
    () {
      final bytes = fixture('cloud-mixed.zip');
      final board = BoardArchive.open('note.zip', bytes);
      expect(board.canExportCloudNote, isTrue);
      final result = ZipDecoder().decodeBytes(board.cloudNoteBytes());
      expect(result.findFile('lesson/page_mdb/data.mdb'), isNull);
      expect(result.findFile('lesson/page_mdb'), isNull);
      expect(result.findFile('lesson/p1/router.bin'), isNotNull);
      final full = header.Header.fromBuffer(
        result.findFile('lesson/p1/header.bin')!.readBytes()!,
      );
      expect(full.width, board.current.size.width);
      expect(full.height, board.current.size.height);
      expect(full.duration.toInt(), 875);
      expect(board.bytes(), bytes);
      board.current.draw(stroke());
      expect(
        BoardArchive.open('new.zip', board.cloudNoteBytes()).current.strokes,
        hasLength(1),
      );
      expect(
        ZipDecoder()
            .decodeBytes(board.bytes())
            .findFile('lesson/page_mdb/data.mdb'),
        isNotNull,
      );
    },
  );
  test(
    'Sketch picture bounds and stacking match every native recording callback',
    () {
      final bytes = fixture('sketch-image-recording.zip');
      final doc = BoardArchive.open('recording.zip', bytes);
      final trace =
          jsonDecode(utf8.decode(fixture('image-recording-frames.json')))
              as List;
      for (final raw in [...trace, ...trace.reversed]) {
        final frame = doc.current.timeline!.seek(raw['ms']);
        final layers = <Object>[];
        var strokeIndex = 0;
        for (final art in frame.artwork) {
          while (strokeIndex < art.beforeStroke) {
            layers.add('stroke');
            strokeIndex++;
          }
          final bmp = art.sketchBitmap!;
          final m = bmp.displayMatrix(art.transform, 64);
          final corners = <double>[];
          for (final p in [
            Offset.zero,
            const Offset(64, 0),
            const Offset(64, 40),
            const Offset(0, 40),
          ]) {
            corners.addAll([
              m[0] * p.dx + m[1] * p.dy + m[2],
              m[3] * p.dx + m[4] * p.dy + m[5],
            ]);
          }
          layers.add({'image': bmp.filename, 'corners': corners});
        }
        layers.addAll(
          List.filled(frame.strokes.length - strokeIndex, 'stroke'),
        );
        expect(layers, raw['layers'], reason: 'native frame ${raw["ms"]}ms');
      }
      expect(
        doc.current.artwork.single.sketchBitmap!.opacity,
        closeTo(128 / 255, 0.00001),
      );
      expect(doc.bytes(), bytes);
    },
  );
  test(
    'Sketch edit keeps both picture files and preserves their original action records',
    () {
      final bytes = fixture('sketch-images.zip');
      final doc = BoardArchive.open('illustration.zip', bytes);
      expect(doc.current.unrendered, isEmpty);
      final original = doc.read('illustration/actions.bin');
      final missing = BoardFile.open('actions.bin', original);
      expect(missing.unrendered, contains('缺少图片 res/icons/upper.jpg'));
      expect(missing.bytes(), original);
      final before = (doc.current.message as sk.DrawBoard)
          .boardBody
          .actionContent
          .map((r) => r.writeToBuffer())
          .toList();
      doc.current.draw(stroke());
      final edited = BoardArchive.open('updated.zip', doc.bytes());
      expect(edited.current.strokes.length, 3);
      expect(edited.current.artwork.map((art) => art.beforeStroke), [1, 1]);
      for (final name in ['res/center.png', 'res/icons/upper.jpg']) {
        expect(
          edited.read('illustration/$name'),
          doc.read('illustration/$name'),
        );
      }
      final actions =
          (edited.current.message as sk.DrawBoard).boardBody.actionContent;
      expect(actions.take(before.length).map((r) => r.writeToBuffer()), before);
    },
  );
  test('native WebP page has independent bitmap and view widths', () {
    final zip = fixture('native-simple-page.zip');
    final doc = BoardArchive.open('native.zip', zip);
    expect(doc.current.size, const Size(640, 480));
    expect(doc.current.strokes, hasLength(3));
    final first = doc.current.strokes.first.points.first;
    doc.setSimpleWidth(320);
    expect(doc.current.size, const Size(320, 240));
    expect(doc.current.strokes.first.points.first, first);
    expect(doc.bytes(), zip);
  });
  test(
    'Sketch playback uses the native two-segment clock and partial strokes',
    () {
      final bytes = fixture('sketch-recording.zip');
      final doc = BoardArchive.open('recording.zip', bytes);
      final timeline = doc.current.timeline!;
      expect(timeline.durationMs, 2000);
      expect(timeline.clips.map((clip) => clip.startMs), [0, 1200]);
      expect(timeline.clipAt(1199)!.filename, 'first.wav');
      expect(timeline.clipAt(1200)!.filename, 'second.wav');
      expect(timeline.clipAt(2000), isNull);
      expect(doc.sketchAudio('first.wav')!.sublist(0, 4), [82, 73, 70, 70]);
      List<int> points(int ms) =>
          timeline.seek(ms).strokes.map((s) => s.points.length).toList();
      expect(points(49), isEmpty);
      expect(points(50), [1]);
      expect(points(350), [2]);
      expect(points(700), [2]);
      expect(points(900), isEmpty);
      expect(points(950), [3]);
      expect(
        timeline.seek(950).strokes.first.points.first,
        const Offset(60, 45),
      );
      expect(
        timeline.seek(700).strokes.first.points.first,
        const Offset(45, 45),
      );
      expect(points(1199), [3]);
      expect(points(1200), isEmpty);
      expect(points(1399), isEmpty);
      expect(points(1400), [1]);
      expect(points(1800), [2]);
      expect(points(2000), [3]);
      expect(points(910), isEmpty);
      expect(points(550), [2]);
      expect(points(2000), [3]);
      expect(doc.bytes(), bytes);
      doc.current.draw(stroke());
      final exported = BoardArchive.open('edited.zip', doc.bytes());
      expect(exported.current.strokes, hasLength(2));
      expect(exported.current.timeline!.durationMs, 2000);
      expect(exported.sketchAudio('second.wav'), doc.sketchAudio('second.wav'));
      final body = (exported.current.message as sk.DrawBoard).boardBody;
      expect(
        body.actionContent
            .lastWhere((a) => a.type == sk.ActionEnum.ACTION_AUDIO_STOP)
            .hasResetData(),
        isTrue,
      );
    },
  );
  test(
    'V5 transform replay and reverse seeking agree with all native graph coordinates',
    () {
      final doc = BoardArchive.open(
        'transform.zip',
        fixture('sketch-transform.zip'),
      ).current;
      final native =
          jsonDecode(utf8.decode(fixture('transform-frames.json'))) as List;
      for (final frame in [...native, ...native.reversed]) {
        final ms = frame['ms'] as int;
        final expected = frame['strokes'] as List;
        final strokes = doc.timeline!.seek(ms).strokes;
        expect(
          strokes.length,
          expected.length,
          reason: 'stroke count at $ms ms',
        );
        for (var i = 0; i < strokes.length; i++) {
          final points = expected[i] as List;
          expect(strokes[i].width, 6);
          expect(
            strokes[i].points.length,
            points.length,
            reason: 'point count at $ms ms',
          );
          for (var j = 0; j < points.length; j++) {
            expect(
              strokes[i].points[j].dx,
              closeTo(points[j][0], 0.0001),
              reason: 'x at $ms ms',
            );
            expect(
              strokes[i].points[j].dy,
              closeTo(points[j][1], 0.0001),
              reason: 'y at $ms ms',
            );
          }
        }
      }
      expect(doc.unrendered, isEmpty);
      final still = BoardFile.open(
        'actions.bin',
        fixture('sketch-transform.bin'),
      );
      expect(still.strokes.first.points.first, const Offset(114, 57));
      still.draw(stroke());
      final again = BoardFile.open('actions.bin', still.bytes());
      expect(again.strokes, hasLength(3));
      expect(
        (again.strokes.last.points.last - const Offset(65, 42)).distance,
        lessThan(0.0001),
      );
    },
  );
  test(
    'Chromium touch, zoom, draw and redo produce the same geometry in the original APK',
    () {
      final input = BoardFile.open(
        'actions.bin',
        fixture('sketch-transform.bin'),
      );
      final edited = BoardFile.open(
        'actions.bin',
        fixture('web-transform.bin'),
      );
      final base = (input.message as sk.DrawBoard).boardBody.actionContent;
      final records = (edited.message as sk.DrawBoard).boardBody.actionContent;
      for (var i = 0; i < base.length; i++) {
        expect(records[i].writeToBuffer(), base[i].writeToBuffer());
      }
      expect(records.skip(base.length).map((r) => r.type), [
        sk.ActionEnum.ACTION_TRANS,
        sk.ActionEnum.ACTION_ZOOM,
        sk.ActionEnum.ACTION_MODE,
        sk.ActionEnum.ACTION_GRAPH,
        sk.ActionEnum.ACTION_TOUCH,
      ]);
      final native =
          jsonDecode(utf8.decode(fixture('transform-edit-frames.json')))
              as List;
      final points = native.last['strokes'] as List;
      expect(points.length, 3);
      expect(edited.strokes.length, points.length);
      for (var i = 0; i < points.length; i++) {
        expect(edited.strokes[i].points.length, points[i].length);
        for (var k = 0; k < points[i].length; k++) {
          expect(
            edited.strokes[i].points[k].dx,
            closeTo(points[i][k][0], 0.0001),
          );
          expect(
            edited.strokes[i].points[k].dy,
            closeTo(points[i][k][1], 0.0001),
          );
        }
      }
    },
  );
  for (var v = 1; v <= 5; v++) {
    test('Sketch V$v retains version and action wrapping after editing', () {
      final head = sk.BoardHead(version: v, width: 500, height: 300);
      final buffer = v == 1
          ? sk.DrawBoardV1(
              boardHead: head,
              boardBodyV1: sk.BoardBodyV1(),
            ).writeToBuffer()
          : sk.DrawBoard(
              boardHead: head,
              boardBody: sk.BoardBody(),
            ).writeToBuffer();
      final doc = BoardFile.open('actions.bin', buffer);
      doc.draw(stroke(shape: PenShape.rectangle));
      final loaded = BoardFile.open('actions.bin', doc.bytes());
      expect(loaded.size, const Size(500, 300));
      final rectangle = loaded.strokes.single;
      expect(rectangle.shape, PenShape.free);
      expect(rectangle.points, [
        const Offset(39.5, 22),
        for (final corner in const [
          Offset(65, 22),
          Offset(65, 42),
          Offset(14, 42),
          Offset(14, 22),
        ]) ...[corner, corner],
        const Offset(40, 22),
      ]);
      final actions = v == 1
          ? (loaded.message as sk.DrawBoardV1).boardBodyV1.actionContent
          : (loaded.message as sk.DrawBoard).boardBody.actionContent.map(
              (a) => a.action,
            );
      expect(
        sk.ActionModeConfig.fromBuffer(actions.first.value).mode,
        sk.ActionModeConfig_Mode.ACTION_WRITING,
      );
      expect(loaded.strokes.single.argb.toUnsigned(32), 0xff123456);
      if (v == 1) {
        final parsed = sk.DrawBoardV1.fromBuffer(doc.bytes());
        expect(parsed.boardHead.version, v);
        expect(
          parsed.boardBodyV1.actionContent.last.typeUrl,
          endsWith('/ActionTouchEvent'),
        );
      } else {
        final parsed = sk.DrawBoard.fromBuffer(doc.bytes());
        expect(parsed.boardHead.version, v);
        expect(
          parsed.boardBody.actionContent.last.type,
          sk.ActionEnum.ACTION_TOUCH,
        );
      }
    });
  }
  test(
    'V5 undo and redo restore the recorded snapshot, including an empty root',
    () {
      final doc = BoardFile.open('actions.bin', fixture('art-actions.bin'));
      final body = (doc.message as sk.DrawBoard).boardBody;
      final sample = BoardArchive.open(
        'recording.zip',
        fixture('sketch-recording.zip'),
      );
      final source =
          (sample.current.message as sk.DrawBoard).boardBody.actionContent;
      final restore = source.firstWhere(
        (a) => a.type == sk.ActionEnum.ACTION_PREV,
      );
      body.actionContent.add(restore);
      doc.refresh();
      expect(doc.strokes.single.points.first, const Offset(60, 45));
      body.actionContent.add(
        sk.ActionContent(
          type: sk.ActionEnum.ACTION_NEXT,
          action: Any(typeUrl: 'type.googleapis.com/ActionNextAction'),
        ),
      );
      doc.refresh();
      expect(doc.strokes, isEmpty);
      doc.draw(stroke(shape: PenShape.ellipse));
      final oval = doc.strokes.single;
      expect(oval.shape, PenShape.free);
      expect(oval.points.length, greaterThan(16));
      final touch = sk.ActionTouchEvent.fromBuffer(
        body.actionContent.last.action.value,
      );
      expect(
        touch.touchEvent.map((event) => Offset(event.x, event.y)),
        containsAll(const [
          Offset(65, 32),
          Offset(39.5, 42),
          Offset(14, 32),
          Offset(39.5, 22),
        ]),
      );
    },
  );
  test('unused native shape modes retain payloads and generate no graph', () {
    final original = fixture('sketch-shapes/raw-v5.bin');
    final file = BoardFile.open('raw-v5.bin', original);
    final before = (file.message as sk.DrawBoard).boardBody.actionContent;
    final records = before.map((a) => a.writeToBuffer()).toList();
    expect(file.strokes.single.points, const [Offset(40, 45), Offset(175, 60)]);
    expect(file.bytes(), original);
    file.draw(
      Ink(
        const [Offset(88, 90), Offset(50, 30)],
        0xff123456,
        5,
        shape: PenShape.ellipse,
      ),
    );
    final loaded = BoardFile.open('actions.bin', file.bytes());
    final points = loaded.strokes.last.points;
    expect(loaded.strokes.length, 2);
    expect(points.first, isNot(points.last));
    expect((points.first - points.last).distance, lessThan(3.0));
    for (final p in points) {
      final x = (p.dx - 69) / 19, y = (p.dy - 60) / 30;
      expect(x * x + y * y, closeTo(1, 0.00001));
    }
    final after = (loaded.message as sk.DrawBoard).boardBody.actionContent;
    expect(after.take(records.length).map((a) => a.writeToBuffer()), records);
  });
  test('zero-area Sketch shapes keep their point or straight segment', () {
    final file = BoardFile.open(
      'raw-v5.bin',
      fixture('sketch-shapes/raw-v5.bin'),
    );
    for (final shape in [PenShape.rectangle, PenShape.ellipse]) {
      for (final endpoints in const [
        [Offset(12, 15)],
        [Offset(42, 70), Offset(42, 20)],
        [Offset(80, 30), Offset(10, 30)],
      ]) {
        file.draw(Ink(endpoints, 0xff123456, 3, shape: shape));
        expect(file.strokes.last.points, endpoints);
      }
    }
  });
  test(
    'V2 appends to a transformed source snapshot and keeps its original graph bytes',
    () {
      final file = BoardFile.open(
        'actions.bin',
        fixture('sketch-shapes/raw-v2.bin'),
      );
      final board = file.message as sk.DrawBoard;
      final source = board.boardBody.actionContent.last.graphSnapshot;
      source.matrix[2] = 13;
      source.childExtendMatrix[5] = -7;
      final subtree = source.childGraph.single.writeToBuffer();
      file.refresh();
      expect(file.strokes.single.points.first, const Offset(53, 38));
      file.draw(stroke(shape: PenShape.rectangle));
      final added = board.boardBody.actionContent.last.graphSnapshot;
      expect(added.name, 'source-root');
      expect(added.childGraph.first.writeToBuffer(), subtree);
      expect(file.strokes.length, 2);
      expect(file.strokes.last.points.first, const Offset(39.5, 22));
      file.draw(Ink([const Offset(65, 42)], 0, 5, erase: true));
      expect(file.strokes.single.points.first, const Offset(53, 38));
      expect(
        board.boardBody.actionContent.last.graphSnapshot.childGraph.first
            .writeToBuffer(),
        subtree,
      );
    },
  );
  test('V2 requires a touch snapshot and V3 reads the config on DOWN', () {
    for (final v in [2, 3]) {
      final original = BoardFile.open(
        'raw.bin',
        fixture('sketch-shapes/raw-v5.bin'),
      );
      final board = original.message as sk.DrawBoard;
      board.boardHead.version = v;
      final file = BoardFile.open('actions.bin', board.writeToBuffer());
      expect(file.strokes, isEmpty);
      file.draw(stroke(shape: PenShape.ellipse));
      final reopened = BoardFile.open('web.bin', file.bytes());
      expect(reopened.strokes.single.points, contains(const Offset(65, 32)));
      final last = (file.message as sk.DrawBoard).boardBody.actionContent.last;
      if (v == 2) {
        expect(last.hasGraphSnapshot(), isTrue);
      } else {
        expect(
          last.resetData.modeConfig,
          sk.ActionModeConfig_Mode.ACTION_WRITING,
        );
        expect(last.resetData.graphConfig.color.toUnsigned(32), 0xff123456);
      }
    }
  });
  test(
    'Blackboard preserves untouched archive bytes and reloads stroke data',
    () {
      final bytes = fixture('schema-page.zip');
      final doc = BoardArchive.open('page.zip', bytes);
      expect(doc.bytes(), bytes);
      doc.current.draw(stroke());
      final after = BoardArchive.open('page.zip', doc.bytes());
      expect(after.current.strokes.single.points.last, const Offset(65, 42));
      expect(after.current.strokes.single.argb.toUnsigned(32), 0xff123456);
      after.current.draw(Ink([const Offset(65, 42)], 0, 10, erase: true));
      expect(
        BoardArchive.open('page.zip', after.bytes()).current.strokes,
        isEmpty,
      );
    },
  );
}
