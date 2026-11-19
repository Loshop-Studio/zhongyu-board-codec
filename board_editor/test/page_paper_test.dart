import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/Header.pb.dart' as header;
import 'package:zy_board_editor/generated/board/PageHeader.pb.dart' as legacy;
import 'package:zy_board_editor/generated/board/RouterRecord.pb.dart' as router;
import 'package:fixnum/fixnum.dart';

void main() {
  final input = File(
    '../reports/evidence/board/ruled-paper/native-paper.zip',
  ).readAsBytesSync();
  BoardArchive open() => BoardArchive.open('native.zip', input);
  test('a change to an old short page header stays local to that page', () {
    final sample = BoardArchive.blankBlackboard();
    sample.addBlackboardPage();
    sample.changed['lesson/p2/header.bin'] = legacy.PageHeader(
      duration: Int64(143),
    ).writeToBuffer();
    final book = BoardArchive.open('old.zip', sample.bytes(), pageIndex: 1);
    final first = book.read('lesson/p1/header.bin'),
        root = book.read('lesson/header.bin');
    final page = book.current as BlackboardPage;
    expect(
      page.setPaper(
        color: 0,
        ruling: PaperRuling.grid,
        lineColor: 0xff223344,
        spacing: 36,
      ),
      true,
    );
    final next = BoardArchive.open('new.zip', book.bytes(), pageIndex: 1);
    expect(next.read('lesson/p1/header.bin'), first);
    expect(next.read('lesson/header.bin'), root);
    final local = header.Header.fromBuffer(next.read('lesson/p2/header.bin'));
    expect(
      [local.width, local.height, local.duration.toInt()],
      [1200, 900, 143],
    );
    expect(next.current.background, 0);
    expect((next.current as BlackboardPage).ruling, PaperRuling.grid);
  });
  test(
    'recorded ruling honors line width, command boundaries and backwards seeks',
    () {
      final page = open().current as BlackboardPage;
      expect(page.ruling, PaperRuling.grid);
      expect(page.paperLines.lineWidth, 3);
      final replay = page.replay;
      expect(replay.seek(176).paperLines!.lineColor, 0);
      final lined = replay.seek(177);
      expect(lined.background.toUnsigned(32), 0xfff2f7fd);
      expect(lined.paperLines!.lineWidth, 2);
      expect(lined.paperLines!.lineSpace, 32);
      expect(lined.paperCamera, page.camera);
      expect(replay.seek(741).paperLines!.lineType.value, 0);
      final grid = replay.seek(742);
      expect(grid.paperLines!.lineType.value, 1);
      expect(grid.paperLines!.lineWidth, 4);
      expect(replay.seek(850).paperCamera, page.camera);
      expect(replay.seek(400).paperLines!.lineSpace, 32);
      expect(page.paperLines.lineWidth, 3);
    },
  );
  test(
    'paper changes update the header and current command shard, preserving recorded history',
    () {
      final book = open(), page = book.current as BlackboardPage;
      expect(
        page.setPaper(
          color: page.background,
          ruling: PaperRuling.grid,
          lineColor: page.paperLines.lineColor,
          spacing: 40,
        ),
        false,
      );
      expect(book.bytes(), input);
      page.setPaper(
        color: 0xfff1f3fc,
        ruling: PaperRuling.horizontal,
        lineColor: 0xff7947a0,
        spacing: 24,
      );
      expect(book.pendingPreviews, contains(page.name));
      final clone = BoardArchive.open('edited.zip', book.bytes());
      final copy = clone.current as BlackboardPage;
      expect(copy.ruling, PaperRuling.horizontal);
      expect(copy.paperLines.lineSpace, 24);
      expect(copy.pageAudio.durationMs, 1263);
      final h = header.Header.fromBuffer(clone.read('${page.dir}header.bin'));
      expect(h.lastBackgroundLineConfig.hasLineWidth(), false);
      final refs = router.RouterRecord.fromBuffer(
        clone.read('${page.dir}router.bin'),
      );
      final command = cmd.CommandSource.fromBuffer(
        clone.read(page.dir + refs.commandRecord.last.fileName),
      ).commandInfo.single;
      expect(command.isPlay, false);
      final config = cmd.CommandSource_CommandInfo_Config.fromBuffer(
        command.data,
      );
      expect(config.originBackground, config.lastBackground);
      expect(config.originBackgroundLineConfig.lineType.value, 1);
      expect(config.lastBackgroundLineConfig.lineWidth, 3);
      expect(copy.replay.seek(800).paperLines!.lineWidth, 4);
      expect(copy.replay.seek(1263).paperLines!.lineSpace, 24);
      final saved = clone.bytes();
      expect(
        () => copy.setPaper(
          color: 0,
          ruling: PaperRuling.grid,
          lineColor: 0,
          spacing: 0,
        ),
        throwsFormatException,
      );
      expect(clone.bytes(), saved);
      copy.setPaper(
        color: copy.background,
        ruling: PaperRuling.plain,
        lineColor: 0,
        spacing: 0,
      );
      expect(copy.paperLines.lineColor, 0);
    },
  );
}
