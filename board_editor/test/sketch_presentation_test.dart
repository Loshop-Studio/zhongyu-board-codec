import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  const evidence = '../reports/evidence';
  final source = File(
    '$evidence/board/sketch-presentations.zip',
  ).readAsBytesSync();

  test('V2 and V4–5 use the WebView action and V3 uses the snapshot', () {
    final archive = BoardArchive.open('slides.zip', source);
    for (var version = 2; version <= 5; version++) {
      archive.select(archive.entries.indexOf('slides-v$version/actions.bin'));
      final art = archive.current.artwork.single;
      final deck = art.presentation!;
      expect(deck.filename, 'lesson.html');
      expect(deck.hasHtml, isTrue);
      expect([deck.width, deck.height], version == 3 ? [320, 200] : [480, 300]);
      expect(
        art.transform,
        version == 3
            ? [1, 0, 54, 0, 1, 47, 0, 0, 1]
            : [.625, 0, 200, 0, .625, 180, 0, 0, 1],
      );
      expect(deck.resource('media/tile.png')!.take(4), [137, 80, 78, 71]);
      for (final path in [
        '../audio/first.wav',
        'https://example.invalid/a',
        '/other',
        'css/missing.png',
      ]) {
        expect(deck.resource(path), isNull);
      }
    }
    expect(archive.bytes(), source);
    final raw = archive.read('slides/actions.bin');
    final missing = BoardFile.open('actions.bin', raw);
    expect(
      missing.unrendered,
      contains('课件资源 res/ppt/lesson.html 或 res/lesson.html'),
    );
    expect(missing.bytes(), raw);
  });

  test('opens the recorder output directly under res/', () {
    final archive = BoardArchive.open(
      'native.zip',
      File('$evidence/board/native-sketch-presentation.zip').readAsBytesSync(),
    );
    final art = archive.current.artwork.single;
    final deck = art.presentation!;
    expect(archive.current.unrendered, isEmpty);
    expect(art.transform, [1, 0, 0, 0, 1, 0, 0, 0, 1]);
    expect([deck.width, deck.height], [640, 480]);
    expect(deck.hasHtml, isTrue);
    expect(
      deck.resource('js/deck.js'),
      archive.read('native-presentation/res/js/deck.js'),
    );
  });

  test(
    'resource lookup stays with the selected entry when both layouts exist',
    () {
      final original = BoardArchive.open('test.zip', source);
      final archive = BoardArchive.fromDirectory('test', {
        'slides/actions.bin': original.read('slides/actions.bin'),
        'slides/res/lesson.html': Uint8List.fromList([1]),
        'slides/res/js/only-in-writer-folder.js': Uint8List.fromList([2]),
        'slides/res/ppt/lesson.html': Uint8List.fromList([3]),
      });
      final deck = archive.current.artwork.single.presentation!;
      expect(deck.resource('lesson.html'), [3]);
      expect(deck.resource('js/only-in-writer-folder.js'), isNull);
    },
  );

  test(
    'recorded insertion follows the audio clock and empty stop snapshot',
    () {
      final archive = BoardArchive.open('slides.zip', source);
      archive.select(archive.entries.indexOf('slides-recording/actions.bin'));
      final timeline = archive.current.timeline!;
      expect(timeline.durationMs, 1200);
      for (final time in [0, 399, 400, 1199, 1200, 1130, 1, 400]) {
        final layers = timeline.seek(time).artwork;
        if (time >= 400 && time < 1200) {
          expect(layers.single.presentation!.hasHtml, isTrue);
          expect(layers.single.transform, [
            .625,
            0,
            200,
            0,
            .625,
            180,
            0,
            0,
            1,
          ]);
        } else {
          expect(layers, isEmpty);
        }
      }
    },
  );

  test(
    'exported strokes and deck match the final graph of the original player',
    () {
      final export = BoardArchive.open(
        'web.zip',
        File('$evidence/board/web-sketch-presentation.zip').readAsBytesSync(),
      );
      final original = jsonDecode(
        File('$evidence/art/presentation-graphs.json').readAsStringSync(),
      )['apps'][0]['graphs'];
      for (final name in [
        'slides',
        'slides-v2',
        'slides-v3',
        'slides-v4',
        'slides-v5',
        'slides-recording',
      ]) {
        export.select(export.entries.indexOf('$name/actions.bin'));
        final frames = original[name] as List<dynamic>;
        for (final frame
            in export.current.timeline == null ? [frames.last] : frames) {
          final timed = export.current.timeline?.seek(frame['ms']);
          final artwork = timed?.artwork ?? export.current.artwork;
          final strokes = timed?.strokes ?? export.current.strokes;
          final layers = <Object>[];
          for (final art in artwork) {
            layers.add({
              'entry': art.presentation!.filename,
              'width': art.presentation!.width,
              'height': art.presentation!.height,
              'matrix': art.transform,
            });
          }
          layers.addAll(List.filled(strokes.length, 'stroke'));
          expect(layers, frame['layers'], reason: '$name at ${frame["ms"]}');
        }
      }
    },
  );
}
