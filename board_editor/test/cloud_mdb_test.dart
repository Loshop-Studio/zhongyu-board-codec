import 'dart:io';
import 'dart:typed_data';
import 'dart:ui';
import 'package:archive/archive.dart';
import 'package:zy_board_editor/generated/board/Command.pb.dart' as cmd;
import 'package:zy_board_editor/generated/board/GraphSnapshot.pb.dart' as snap;
import 'package:zy_board_editor/generated/board/enums/GraphEnum.pbenum.dart'
    as graph;
import 'package:zy_board_editor/generated/board/utils/Matrix.pb.dart' as mat;

import 'package:flutter_test/flutter_test.dart';
import 'package:zy_board_editor/board_file.dart';
import 'package:zy_board_editor/cloud_mdb.dart';

void main() {
  Uint8List fixture(String name) =>
      File('../reports/evidence/board/page_mdb/$name.mdb').readAsBytesSync();

  test('chooses the latest transaction and decodes native catalog strings', () {
    final native = CloudMdbStore.read(fixture('data'));
    expect(native.counts, hasLength(24));
    expect(native.counts.values, everyElement(1));
    expect(native.rows['PageEntity']![1]!.string('dirName'), 'p-local');
    expect(native.rows['TextInfoEntity']![1]!.string('content'), '本地画板样本');
  });

  test(
    'restores native graph commands, per-page sources and original order',
    () {
      final d = CloudInkDocument(fixture('new-notebook'))..openPage(0);
      expect(d.board.size.width, 1200);
      expect(d.board.strokes.single.points, hasLength(11));
      expect(d.board.strokes.single.points.first.dx, closeTo(303.947, 0.001));
      d.openPage(1);
      expect(d.board.strokes, isEmpty);
      final native = CloudInkDocument(fixture('native-v6-two-pages'))
        ..openPage(0);
      expect(native.board.strokes, hasLength(3));
      expect(native.board.strokes.first.width, 9);
      expect(native.board.strokes.first.points.first.dx, 80);
      expect(native.eventAt(0).id, 1);
    },
  );

  test(
    'edits only existing paint/points, undo restores all original bytes',
    () {
      final input = fixture('native-v6-two-pages');
      final d = CloudInkDocument(input)..openPage(0);
      final before = d.board.strokes.first;
      d.edit(0, color: 0xffd32f2f, width: 12, smooth: true);
      final reopened = CloudInkDocument(d.store.bytes)..openPage(0);
      final edited = reopened.board.strokes.first;
      expect(edited.argb.toUnsigned(32), 0xffd32f2f);
      expect(edited.width, 12);
      expect(edited.points.first, before.points.first);
      expect(edited.points.last, before.points.last);
      expect(edited.points[1], isNot(before.points[1]));
      expect(reopened.board.strokes[1].points, d.board.strokes[1].points);
      d.undo();
      expect(d.store.bytes, input);
      d.redo();
      expect(d.store.bytes, reopened.store.bytes);
      expect(input, fixture('native-v6-two-pages'));
    },
  );

  test(
    'a companion snapshot selects the visible source and transforms point edits',
    () {
      final raw = fixture('native-v6-two-pages');
      final original = CloudInkDocument(raw)..openPage(0);
      final pageName = original.pages[0].string('dirName');
      final chunk = original.store.rows['TouchRecordEntity']![1]!.string(
        'fileName',
      );
      final node = snap.PageSnapshot_GraphSnapshot(
        graphEnum: graph.GraphEnum.STROKE_GRAPH,
        sourceFileName: chunk,
        sourceId: 1,
        matrix: mat.Matrix(scaleX: 1, scaleY: 1, perSp2: 1, transX: 30),
      );
      final snapshot = snap.PageSnapshot(
        cameraMatrix: mat.Matrix(scaleX: 1, scaleY: 1, perSp2: 1),
        graphSnapshot: snap.PageSnapshot_GraphSnapshot(
          graphEnum: graph.GraphEnum.GROUP_GRAPH,
          childGraph: [node],
        ),
      );
      final archive = Archive()
        ..addFile(
          ArchiveFile.bytes(
            'lesson/$pageName/snapshot.bin',
            snapshot.writeToBuffer(),
          ),
        );
      final d = CloudInkDocument(
        raw,
        member: 'lesson/page_mdb/data.mdb',
        archive: archive,
      )..openPage(0);
      expect(d.board.strokes, hasLength(1));
      expect(d.eventAt(0).id, 2);
      final point = d.board.strokes.single.points[1];
      final stored = d.store.children(d.eventAt(0), 'TouchInfoEntity')[1];
      expect(point.dx, stored.real('x') + 30);
      d.edit(0, movePoint: (1, point + const Offset(2, 0)));
      d.openPage(0);
      expect(d.board.strokes.single.points[1].dx, point.dx + 2);
      d.undo();
      expect(d.store.bytes, raw);
    },
  );

  test(
    'a dirty page resumes at the inclusive command index after its snapshot',
    () {
      final store = CloudMdbStore.read(fixture('new-notebook'));
      final d = ByteData.sublistView(store.bytes),
          page = store.rows['PageEntity']![1]!;
      final chunks = store.rows['CommandRecordEntity']!.values
          .where((e) => e.long('recordId') == 1)
          .toList();
      final root = cmd.CommandSource_CommandInfo_GraphData.fromBuffer(
        store.children(chunks.first, 'CommandInfoEntity').first.blob('data'),
      ).graphId;
      final snapFile = snap.PageSnapshot(
        cameraMatrix: mat.Matrix(scaleX: 1, scaleY: 1, perSp2: 1),
        graphSnapshot: snap.PageSnapshot_GraphSnapshot(
          id: root,
          childGraph: [
            snap.PageSnapshot_GraphSnapshot(
              id: 'existing',
              graphEnum: graph.GraphEnum.GROUP_GRAPH,
            ),
          ],
        ),
      );
      final zip = Archive()
        ..addFile(
          ArchiveFile.bytes('p1/snapshot.bin', snapFile.writeToBuffer()),
        );
      // The fixture's page already stores the string "p1". Use it as a short
      // checkpoint name without moving or reallocating any ObjectBox record.
      int ref(MdbRow row, String field) {
        final p = row.scalarOffset(field);
        return p + d.getUint32(p, Endian.little);
      }

      final cursor = page.scalarOffset('commandFileName'),
          name = ref(chunks.last, 'fileName');
      d.setUint32(cursor, ref(page, 'dirName') - cursor, Endian.little);
      d.setUint32(name, 2, Endian.little);
      store.bytes.setRange(name + 4, name + 7, [112, 49, 0]);
      d.setUint8(page.scalarOffset('isChange'), 1);
      int count() => (CloudInkDocument(
        store.bytes,
        member: 'data.mdb',
        archive: zip,
      )..openPage(0)).board.strokes.length;
      d.setInt32(page.scalarOffset('commandIndex'), 0, Endian.little);
      expect(count(), 1);
      d.setInt32(page.scalarOffset('commandIndex'), 1, Endian.little);
      expect(count(), 0);
      zip.addFile(
        ArchiveFile.bytes(
          'p1/snapshot.bin',
          snap.PageSnapshot().writeToBuffer(),
        ),
      );
      expect(count(), 1);
    },
  );

  test('rejects damaged or unrelated MDBs', () {
    expect(() => CloudMdbStore.read(Uint8List(512)), throwsFormatException);
    expect(
      () => CloudMdbStore.read(Uint8List.sublistView(fixture('data'), 0, 8192)),
      throwsFormatException,
    );
  });
}
