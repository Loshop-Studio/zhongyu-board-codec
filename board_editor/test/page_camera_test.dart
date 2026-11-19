import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  final input = File(
    '../reports/evidence/board/camera/native.zip',
  ).readAsBytesSync();
  BoardArchive open() => BoardArchive.open('native.zip', input);
  test(
    'native pen-mode pan ignores span while viewing-mode pinch changes scale about the midpoint',
    () {
      final page = open().current as BlackboardPage;
      final replay = page.replay;
      final initial = replay.seek(800).strokes.single.points.first;
      final pan = replay.seek(1340).strokes.single.points.first;
      expect(pan.dx - initial.dx, closeTo(-47, .001));
      expect(pan.dy - initial.dy, closeTo(-36, .001));
      final afterPan = replay.seek(1660).strokes.single.points.first;
      final pinched = replay.seek(2170).strokes.single.points.first;
      expect(pinched.dx, closeTo(afterPan.dx * 1.3662 - 110.8654, .03));
      expect(pinched.dy, closeTo(afterPan.dy * 1.3662 - 90.557, .03));
      expect(
        replay.seek(2557).strokes.single.points.first,
        page.strokes.single.points.first,
      );
      expect(replay.seek(1340).strokes.single.points.first, pan);
    },
  );
  test(
    'camera constraints, simultaneous samples and native final matrix survive reopening',
    () {
      final book = open(), page = book.current as BlackboardPage;
      expect(page.canRecordCamera, isTrue);
      final initial = page.camera;
      final view = PageCameraGesture(page, const Offset(240, 170), 100);
      view.beginPinch(const Offset(240, 170), 100);
      view.move(const Offset(250, 176), 110, 105);
      view.move(const Offset(255, 183), 125, 105);
      expect(view.samples, hasLength(1));
      view.move(const Offset(260, 190), 150, 205);
      expect(view.samples.last.scaleX, 1.5);
      expect(view.samples.last.transX, -100);
      expect(view.samples.last.transY, -65);
      expect(view.save(), isTrue);
      expect(page.camera[0], closeTo(initial[0] * 1.5, .0001));
      expect(page.camera[2], closeTo(initial[2] * 1.5 - 100, .0001));
      final after =
          BoardArchive.open('edited.zip', book.bytes()).current
              as BlackboardPage;
      expect(after.camera, page.camera);
      expect(after.pageAudio.durationMs, 2557 + 100 + 192);
      expect(
        after.replay
            .seek(after.pageAudio.durationMs)
            .strokes
            .single
            .points
            .first,
        after.strokes.single.points.first,
      );
      final clipped = PageCameraGesture(after, Offset.zero, 1000);
      clipped.move(const Offset(10000, 10000), null, 1040);
      expect(clipped.samples.last.transX, closeTo(-after.camera[2], .001));
      expect(clipped.samples.last.transY, closeTo(-after.camera[5], .001));
    },
  );
  test(
    'two contacts in writing mode keep their scale even as the distance changes',
    () {
      final page = open().current as BlackboardPage;
      final pan = PageCameraGesture(
        page,
        const Offset(240, 180),
        100,
        writing: true,
      );
      pan.beginPinch(const Offset(240, 180), 100);
      pan.move(const Offset(212, 160), 145, 150);
      pan.move(const Offset(212, 160), 193, 220);
      expect(pan.samples.map((m) => [m.scaleX, m.transX, m.transY]), [
        [1, -28, -20],
        [1, -28, -20],
      ]);
    },
  );
  test('taps and immobile pans leave all note bytes untouched', () {
    final book = open(), page = book.current as BlackboardPage;
    final view = PageCameraGesture(page, const Offset(200, 150), 100);
    expect(view.save(), isFalse);
    view.move(const Offset(200, 150), null, 145);
    expect(view.save(), isFalse);
    expect(book.bytes(), input);
  });
}
