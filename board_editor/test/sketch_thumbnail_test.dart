import 'dart:io';
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  final input = File(
    '../reports/evidence/board/sketch-thumbnails/native.zip',
  ).readAsBytesSync();
  final pen = Ink(
    [const Offset(50, 200), const Offset(80, 246)],
    0xff203048,
    3,
  );
  BoardArchive open() => BoardArchive.open('native.zip', input);
  Never wrongPage(BlackboardPage _) => throw StateError('Unexpected V6 page');

  test(
    'restore the recorder graph on a touch and keep the paper on an area-only tail',
    () {
      final page = open().current;
      expect(page.strokes.single.argb.toSigned(32), 0xff98324c.toSigned(32));
      expect(page.strokes.single.width, 9);
      expect(page.artwork.single.sketchBitmap!.filename, 'diagram.jpg');
      expect(page.background.toUnsigned(32), 0xffffffff);
      expect(page.sketchDrawArea, const Rect.fromLTRB(50, 45, 600, 445));
      expect(page.sketchPreviewClip, page.sketchDrawArea);
      page.draw(pen);
      expect(page.artwork, hasLength(1));
      expect(page.strokes, hasLength(2));
      expect(page.sketchUsesThumbnailAsSource, isFalse);
    },
  );
  test(
    'only the edited recorder page gets a JPEG, including a missing one beside its header',
    () async {
      final first = open();
      final book = BoardArchive.fromDirectory('examples', {
        for (final f in first.arch.files)
          if (f.isFile) f.name: first.read(f.name),
        for (final f in first.arch.files)
          if (f.isFile && !f.name.endsWith('thumbnail.jpg'))
            f.name.replaceFirst('note/', 'second/'): first.read(f.name),
      });
      book.select(book.entries.indexOf('second/actions.bin'));
      book.current.draw(pen);
      final result = await book.export(
        cloudCopy: false,
        renderPreview: wrongPage,
        renderSketchThumbnail: (p, src) async {
          expect(src, isNull);
          expect(p.strokes, hasLength(2));
          expect(p.artwork.single.sketchBitmap!.filename, 'diagram.jpg');
          return Uint8List.fromList([17]);
        },
      );
      expect(result.skipped, isEmpty);
      final saved = BoardArchive.open('edited.zip', result.bytes);
      expect(saved.read('second/thumbnail.jpg'), [17]);
      expect(
        saved.read('note/thumbnail.jpg'),
        first.read('note/thumbnail.jpg'),
      );
    },
  );
  for (final version in [1, 5]) {
    test(
      'V$version JPEG-backed page opens as one image and tracks unbaked edits',
      () async {
        final legacy = File(
          '../reports/evidence/board/sketch-thumbnails/backing-v$version.zip',
        ).readAsBytesSync();
        final book = BoardArchive.open('backing.zip', legacy);
        expect(book.current.strokes, isEmpty);
        expect(
          book.current.artwork.single.sketchBitmap!.filename,
          'thumbnail.jpg',
        );
        expect(book.current.sketchDrawArea, isNull);
        book.current.draw(pen);
        final revision = book.bytes();
        final restored = BoardArchive.open(
          'backing.zip',
          revision,
          thumbnailActionCounts: book.thumbnailActionCounts,
        );
        expect(restored.current.strokes, hasLength(1));
        expect(restored.current.artwork, hasLength(1));
        expect(
          BoardArchive.open('saved.zip', revision).current.strokes,
          isEmpty,
        );
        final exported = await book.export(
          cloudCopy: false,
          renderPreview: wrongPage,
          renderSketchThumbnail: (page, jpeg) async {
            expect(page.hasThumbnailBacking, isTrue);
            expect(page.strokes, hasLength(1));
            return jpeg!;
          },
        );
        expect(exported.skipped, isEmpty);
      },
    );
  }
  test(
    'a thumbnail failure keeps the JPEG and exports the edited actions',
    () async {
      final book = open();
      book.current.draw(pen);
      final result = await book.export(
        cloudCopy: false,
        renderPreview: wrongPage,
        renderSketchThumbnail: (_, _) async =>
            throw const FormatException('unknown layer'),
      );
      final saved = BoardArchive.open('edited.zip', result.bytes);
      expect(result.skipped.single, contains('unknown layer'));
      expect(saved.read('note/thumbnail.jpg'), book.read('note/thumbnail.jpg'));
      expect(saved.current.strokes, hasLength(2));
    },
  );
}
