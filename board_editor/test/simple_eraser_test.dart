import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';

void main() {
  const dir = '../reports/evidence/board/simple-eraser';
  final input = File('$dir/input.bin').readAsBytesSync();
  final reports =
      jsonDecode(File('$dir/native.json').readAsStringSync()) as List;
  for (final native in reports.first['cases']) {
    test('SimpleBoard original Views: ${native['name']}', () {
      final file = BoardFile.open('remote_draft.bin', input);
      final radius =
          (native['radius'] as num? ?? 40) / (native['zoom'] as num? ?? 1);
      int remembered = 0;
      for (final event in native['contacts']) {
        file.eraseSimpleAt(
          Offset((event[1] as num).toDouble(), (event[2] as num).toDouble()),
          radius,
          beforeChange: () => remembered++,
        );
      }
      expect(
        file.strokes.map((s) => s.argb.toUnsigned(32)).toList(),
        native['surviving_colors'],
      );
      expect(file.dirty, remembered > 0);
      if (!file.dirty) expect(file.bytes(), input);
      if (native['name'] == 'drag') {
        expect(file.bytes(), File('$dir/native-drag.bin').readAsBytesSync());
      }
    });
  }
  test(
    'thin bounds keep their creation radius while the current tool radius changes',
    () {
      final file = BoardFile.open('input.bin', input);
      file.simpleCreationRadius = 6;
      file.draw(
        Ink([const Offset(12, 20), const Offset(100, 20)], 0xff001122, 3),
      );
      final saved = file.simpleBoundsRadii;
      final reopened = BoardFile.open('history.bin', file.bytes())
        ..restoreSimpleBounds(saved);
      expect(reopened.simpleBoundsRadii.last, 6);
      reopened.eraseSimpleAt(const Offset(50, 31), 40);
      expect(
        reopened.strokes.any((s) => s.argb.toUnsigned(32) == 0xff001122),
        isTrue,
      );
      reopened.eraseSimpleAt(const Offset(50, 25), 10);
      expect(
        reopened.strokes.any((s) => s.argb.toUnsigned(32) == 0xff001122),
        isFalse,
      );
    },
  );
}
