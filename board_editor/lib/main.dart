import 'dart:async';
import 'dart:js_interop';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart' hide Ink;
import 'package:flutter/services.dart' show HardwareKeyboard;
import 'package:image/image.dart' as raster;
import 'package:web/web.dart' as web;
import 'board_file.dart';
import 'generated/board/Header.pb.dart' as wire;

part 'page_artwork.dart';
part 'page_preview.dart';
part 'sketch_thumbnail.dart';
part 'paper_view.dart';
part 'cursor_painter.dart';
part 'paper_dialog.dart';
part 'presentation_view.dart';
part 'artwork_dialog.dart';
part 'create_artwork_dialog.dart';
part 'image_picker.dart';
part 'audio_picker.dart';
part 'recording_controls.dart';

void main() => runApp(
  MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff236c62)),
      fontFamily: 'Board Sans',
    ),
    home: const Editor(),
  ),
);

// Android moves a clipped active-layer bitmap, including its pen widths and images.
class _CameraInkView extends StatelessWidget {
  const _CameraInkView(this.delta, this.scale, {required this.child});
  final List<double>? delta;
  final double scale;
  final Widget child;
  @override
  Widget build(BuildContext context) {
    final m = delta;
    if (m == null) return child;
    final transform = _canvasTransform(m, 1)
      ..setEntry(0, 3, m[2] * scale)
      ..setEntry(1, 3, m[5] * scale)
      ..setEntry(3, 0, m[6] / scale)
      ..setEntry(3, 1, m[7] / scale);
    return Transform(
      transform: transform,
      child: ClipRect(child: child),
    );
  }
}

typedef _DocumentRevision = ({
  String name,
  Uint8List bytes,
  int? pageIndex,
  Set<String> pendingPreviews,
  Map<String, int> thumbnailActionCounts,
  bool simple,
  double? simpleWidth,
  List<double>? simpleBoundsRadii,
});

class _ImageDrag {
  _ImageDrag(this.pointer, this.art, this.start);
  final int pointer;
  final PageArtwork art;
  final Offset start;
  Offset delta = Offset.zero;
}

class Editor extends StatefulWidget {
  const Editor({super.key});
  @override
  State<Editor> createState() => _EditorState();
}

class _EditorState extends State<Editor> {
  var file = BoardFile.blank();
  BoardArchive? archive;
  BoardFrame? frame;
  var shape = PenShape.free, dashed = false, pan = false;
  final viewport = TransformationController();
  @override
  void dispose() {
    viewport.dispose();
    super.dispose();
  }

  String get documentName => archive?.name ?? file.name;
  Uint8List documentBytes() => archive?.bytes() ?? file.bytes();

  _DocumentRevision revision() => (
    name: documentName,
    bytes: documentBytes(),
    pageIndex: archive?.index,
    pendingPreviews: {...?archive?.pendingPreviews},
    thumbnailActionCounts: {...?archive?.thumbnailActionCounts},
    simple: file.format == BoardFormat.simple,
    simpleBoundsRadii: file.format == BoardFormat.simple
        ? file.simpleBoundsRadii
        : null,
    simpleWidth: file.format == BoardFormat.simple && archive != null
        ? archive!.sizes[archive!.entries[archive!.index]]?.width
        : null,
  );
  final undo = <_DocumentRevision>[], redo = <_DocumentRevision>[];
  var color = 0xff213836, width = 3.0, erasing = false;
  String? status;
  int selectionVersion = 0;
  int? pointer, selected;
  List<Offset> active = [];
  List<int>? touchTimes;
  int touchEpoch = 0;
  final contacts = <int, Offset>{};
  Offset? dragOrigin;
  Offset dragDelta = Offset.zero;
  bool moveOnce = false, liftContacts = false;
  bool dragImages = false, recordCursor = false, recordCamera = false;
  PageCameraGesture? cameraGesture;
  int penDownTime = 0;

  bool beginWritingContact(
    PointerDownEvent event,
    Offset point,
    BlackboardPage page,
  ) {
    final ms = event.timeStamp.inMilliseconds;
    contacts[event.pointer] = point;
    if (liftContacts || contacts.length > 2) {
      liftContacts = true;
      cameraGesture = null;
      return true;
    }
    if (contacts.length == 1) {
      penDownTime = ms;
      return false;
    }
    if (ms - penDownTime > 48 && active.isNotEmpty) {
      final endpoint = contacts[pointer] ?? active.last;
      active.add(endpoint);
      touchTimes?.add(touchEpoch + ms);
      finish();
    }
    pointer = null;
    active = [];
    touchTimes = null;
    final now = DateTime.now().millisecondsSinceEpoch;
    touchEpoch = now - ms;
    cameraGesture = PageCameraGesture(page, contactCenter, now, writing: true);
    return true;
  }

  double? get contactSpan => contacts.length == 2
      ? (contacts.values.first - contacts.values.last).distance
      : null;

  void startCameraContact(PointerDownEvent e, Offset point) {
    contacts[e.pointer] = point;
    if (contacts.length > 2 || liftContacts) {
      cameraGesture = null;
      liftContacts = true;
      return;
    }
    if (contacts.length == 1) {
      final time = DateTime.now().millisecondsSinceEpoch;
      touchEpoch = time - e.timeStamp.inMilliseconds;
      cameraGesture = PageCameraGesture(file as BlackboardPage, point, time);
    } else {
      cameraGesture?.beginPinch(contactCenter, contactSpan!);
    }
  }

  void endCameraContact(int id, {bool cancelled = false}) {
    if (!contacts.containsKey(id)) return;
    final gesture = cameraGesture;
    if (!cancelled && gesture != null && gesture.samples.isNotEmpty) {
      final before = revision();
      if (gesture.save()) {
        remember(before);
        status = '镜头已追加到本页回放';
      }
    }
    contacts.remove(id);
    liftContacts = contacts.isNotEmpty;
    cameraGesture = null;
  }

  int cursorColor = 0xffff0000;
  double cursorWidth = 20;
  Offset cursorOffset = Offset.zero;
  _ImageDrag? imageDrag;

  double simpleEraserRadius = SimpleBoardEraser.defaultRadius;
  int? simpleEraserPointer;
  Offset? simpleEraserTip;
  bool simpleEraseRemembered = false;
  double get simpleRadiusOnPage =>
      simpleEraserRadius / viewport.value.getMaxScaleOnAxis();

  void touchSimpleEraser(Offset point, {bool lifted = false}) {
    setState(() {
      file.eraseSimpleAt(
        point,
        simpleRadiusOnPage,
        beforeChange: () {
          if (!simpleEraseRemembered) {
            remember(revision());
            simpleEraseRemembered = true;
          }
        },
      );
      simpleEraserTip = lifted ? null : point;
      if (lifted) simpleEraserPointer = null;
    });
  }

  void clearContactState() {
    simpleEraserPointer = null;
    simpleEraserTip = null;
    if (dragImages) status = null;
    contacts.clear();
    pointer = null;
    active = [];
    dragOrigin = null;
    dragDelta = Offset.zero;
    moveOnce = false;
    liftContacts = false;
    dragImages = false;
    recordCursor = false;
    recordCamera = false;
    cameraGesture = null;
    imageDrag = null;
  }

  void finishImageDrag(Offset end) {
    final drag = imageDrag!;
    final delta = end - drag.start;
    try {
      if (delta != Offset.zero) {
        final before = revision();
        (file as BlackboardPage).transformImage(drag.art, move: delta);
        remember(before);
      }
      status = null;
    } on FormatException catch (e) {
      status = e.message;
    }
    setState(() => imageDrag = null);
  }

  Offset get contactCenter =>
      contacts.values.take(2).reduce((a, b) => a + b) /
      math.min(2, contacts.length).toDouble();

  bool endBoardDrag(int id, {required bool cancelled}) {
    if (!contacts.containsKey(id)) return false;
    if (dragOrigin != null) {
      final delta = dragDelta;
      final before = !cancelled && delta != Offset.zero ? revision() : null;
      if (before != null) file.moveSketch(delta);
      setState(() {
        if (before != null) remember(before);
        moveOnce = false;
        dragOrigin = null;
        dragDelta = Offset.zero;
        liftContacts = true;
      });
    }
    contacts.remove(id);
    final consumed = liftContacts;
    if (contacts.isEmpty) liftContacts = false;
    return consumed;
  }

  void showDocument(BoardArchive? bundle, BoardFile next, {String? notice}) {
    setState(() {
      archive = bundle;
      file = next;
      frame = null;
      shape = PenShape.free;
      dashed = false;
      pan = false;
      clearContactState();
      viewport.value = Matrix4.identity();
      undo.clear();
      redo.clear();
      active = [];
      selected = null;
      status = notice;
    });
  }

  void createPageDocument(bool append) {
    final before = revision();
    try {
      if (!append) {
        final bundle = BoardArchive.blankBlackboard();
        ++selectionVersion;
        showDocument(bundle, bundle.current, notice: '已新建 Blackboard 笔记');
        remember(before);
        return;
      }
      final bundle = archive!;
      bundle.addBlackboardPage();
      setState(() {
        file = bundle.current;
        frame = null;
        clearContactState();
        selected = null;
        viewport.value = Matrix4.identity();
        remember(before);
        status = '已添加空白页';
      });
    } on FormatException catch (e) {
      setState(() => status = e.message);
    }
  }

  Future<void> openDirectory() async {
    final input = web.HTMLInputElement()
      ..type = 'file'
      ..webkitdirectory = true
      ..multiple = true;
    Future<void> load() async {
      final selection = input.files;
      if (selection == null || selection.length == 0) return;
      final version = ++selectionVersion;
      try {
        final picked = [
          for (var i = 0; i < selection.length; i++) selection.item(i)!,
        ];
        if (picked.length > BoardArchive.maxMembers ||
            picked.fold<int>(0, (n, f) => n + f.size) >
                BoardArchive.maxMemberBytes) {
          throw const FormatException('选中的目录超过 10000 个文件或 256 MiB');
        }
        final folder = picked.first.webkitRelativePath.split('/').first;
        final contents = <String, Uint8List>{};
        for (final item in picked) {
          if (!mounted || version != selectionVersion) return;
          final path = item.webkitRelativePath;
          if (folder.isEmpty || !path.startsWith('$folder/')) {
            throw const FormatException('浏览器未提供完整的画板目录路径');
          }
          final name = path.substring(folder.length + 1);
          if (name.isEmpty || contents.containsKey(name))
            throw const FormatException('目录含有无效或重复的文件名');
          contents[name] = (await item.arrayBuffer().toDart).toDart
              .asUint8List();
        }
        final bundle = BoardArchive.fromDirectory(folder, contents);
        if (mounted && version == selectionVersion)
          showDocument(bundle, bundle.current, notice: '已打开文件夹 · $folder');
      } catch (e) {
        if (mounted && version == selectionVersion)
          setState(() => status = '打开目录失败 · $e');
      }
    }

    input.onchange = ((web.Event _) {
      load();
    }).toJS;
    input.click();
  }

  Future<void> open() async {
    final input = web.HTMLInputElement()
      ..type = 'file'
      ..accept = '.bin,.zip,application/zip,application/octet-stream';
    Future<void> loadSelection() async {
      final picked = input.files?.item(0);
      if (picked == null) return;
      final version = ++selectionVersion;
      try {
        if (picked.size > 64 * 1024 * 1024)
          throw const FormatException('单文件超过 64 MiB');
        final data = (await picked.arrayBuffer().toDart).toDart.asUint8List();
        final bundle = data.length >= 4 && data[0] == 80 && data[1] == 75
            ? BoardArchive.open(picked.name, data)
            : null;
        var emptySimple = false;
        if (data.isEmpty && picked.name.toLowerCase() != 'remote_draft.bin') {
          if (!mounted || version != selectionVersion) return;
          emptySimple =
              await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('空白 BIN'),
                  content: const Text('按简笔板草稿打开这个空文件？'),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('取消'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('打开草稿'),
                    ),
                  ],
                ),
              ) ??
              false;
          if (!emptySimple) return;
        }
        final next =
            bundle?.current ??
            BoardFile.open(picked.name, data, allowEmptySimple: emptySimple);
        if (!mounted || version != selectionVersion) return;
        showDocument(bundle, next);
      } catch (e) {
        if (mounted && version == selectionVersion)
          setState(() => status = '打开失败 · $e');
      }
    }

    input.onchange = ((web.Event _) {
      loadSelection();
    }).toJS;
    input.click();
  }

  Future<void> save({bool cloudCopy = false}) async {
    final bundle = archive;
    final originalName = documentName.split('/').last;
    final name = cloudCopy
        ? '${originalName.replaceFirst(RegExp(r"\.zip$", caseSensitive: false), "")}-云笔记.zip'
        : originalName;
    try {
      final result = bundle == null
          ? (bytes: file.bytes(), skipped: <String>[])
          : await bundle.export(
              cloudCopy: cloudCopy,
              renderPreview: _pagePreview,
              renderSketchThumbnail: _sketchThumbnail,
            );
      final data = result.bytes;
      final url = web.URL.createObjectURL(web.Blob([data.toJS].toJS));
      (web.HTMLAnchorElement()
            ..href = url
            ..download = name)
          .click();
      Future.delayed(
        const Duration(seconds: 2),
        () => web.URL.revokeObjectURL(url),
      );
      if (mounted && identical(archive, bundle)) {
        final warning = result.skipped.isEmpty
            ? ''
            : ' · 以下页面的预览未更新：${result.skipped.join('，')}';
        setState(() => status = '已导出 $name · ${data.length} 字节$warning');
      }
    } catch (error) {
      if (mounted && identical(archive, bundle))
        setState(() => status = '导出失败 · $error');
    }
  }

  void restore(List<_DocumentRevision> from, List<_DocumentRevision> to) {
    if (from.isEmpty) return;
    final saved = from.last;
    final bundle = saved.pageIndex == null
        ? null
        : BoardArchive.open(
            saved.name,
            saved.bytes,
            pageIndex: saved.pageIndex!,
            thumbnailActionCounts: saved.thumbnailActionCounts,
          );
    if (saved.simpleWidth case final double width)
      bundle?.setSimpleWidth(width);
    bundle?.pendingPreviews.addAll(saved.pendingPreviews);
    final next =
        bundle?.current ??
        BoardFile.open(saved.name, saved.bytes, allowEmptySimple: saved.simple);
    if (saved.simpleBoundsRadii case final radii?)
      next.restoreSimpleBounds(radii);
    setState(() {
      to.add(revision());
      archive = bundle;
      clearContactState();
      from.removeLast();
      file = next;
      frame = null;
      selected = null;
      status = null;
    });
  }

  void remember(_DocumentRevision before) {
    undo.add(before);
    var stored = undo.fold<int>(0, (total, item) => total + item.bytes.length);
    while (undo.length > 1 && (undo.length > 40 || stored > 64 * 1024 * 1024)) {
      stored -= undo.removeAt(0).bytes.length;
    }
    redo.clear();
  }

  Future<void> insertPageArtwork(
    BlackboardPage page,
    ArtworkKind kind, {
    String imageName = '',
    Uint8List? imageBytes,
    Size? imageSize,
  }) async {
    final draft = await showDialog<_ArtworkDraft>(
      context: context,
      builder: (_) => _CreateArtworkDialog(kind, page.size, imageSize, width),
    );
    if (draft == null || !mounted || file != page) return;
    final before = revision();
    try {
      page.createArtwork(
        kind,
        area: draft.area,
        argb: color,
        penSize: draft.penSize,
        content: draft.content,
        imageName: imageName,
        imageBytes: imageBytes,
      );
      setState(() {
        remember(before);
        clearContactState();
        status = '已插入${kind.label}';
      });
    } on FormatException catch (e) {
      setState(() => status = e.message);
    }
  }

  void chooseAudio(BlackboardPage page) {
    final picker = web.HTMLInputElement()
      ..type = 'file'
      ..accept = '.mp3,.wav,.m4a,.aac,.ogg,.opus';
    Future<void> insert() async {
      final picked = picker.files?.item(0);
      if (picked == null) return;
      try {
        final duration = await _audioDuration(picked);
        if (!mounted || file != page) return;
        final gap = await _audioGap(context, picked.name, duration);
        if (gap == null || !mounted || file != page) return;
        final bytes = (await picked.arrayBuffer().toDart).toDart.asUint8List();
        if (!mounted || file != page) return;
        final before = revision();
        final name = page.appendAudio(picked.name, bytes, duration, gapMs: gap);
        setState(() {
          remember(before);
          status = '已追加录音 $name';
        });
      } catch (e) {
        if (mounted && file == page) setState(() => status = '追加录音失败 · $e');
      }
    }

    picker.onchange = ((web.Event _) {
      insert();
    }).toJS;
    picker.click();
  }

  void chooseImage() {
    final owner = file;
    final picker = web.HTMLInputElement()
      ..type = 'file'
      ..accept = 'image/png,image/jpeg,image/webp';
    Future<void> insert() async {
      final picked = picker.files?.item(0);
      if (picked == null) return;
      try {
        if (picked.size > 64 * 1024 * 1024)
          throw const FormatException('图片超过 64 MiB');
        final bytes = (await picked.arrayBuffer().toDart).toDart.asUint8List();
        final size = await _encodedSize(bytes);
        if (!mounted || file != owner) return;
        if (owner is BlackboardPage) {
          await insertPageArtwork(
            owner,
            ArtworkKind.image,
            imageName: picked.name,
            imageBytes: bytes,
            imageSize: size,
          );
          return;
        }
        final placement = await _placeImage(context, size, file.size);
        if (placement == null || !mounted || file != owner) return;
        final before = revision();
        final bundle = archive ?? BoardArchive.fromSketch(file);
        final filename = bundle.insertSketchImage(
          picked.name,
          bytes,
          placement.width,
          math.max(1, (placement.width / size.aspectRatio).round()),
          placement.flag,
        );
        setState(() {
          archive = bundle;
          file = bundle.current;
          remember(before);
          clearContactState();
          status = '已插入 $filename · 图片随 ZIP 导出';
        });
      } catch (e) {
        if (mounted && file == owner) setState(() => status = '插入图片失败 · $e');
      }
    }

    picker.onchange = ((web.Event _) {
      insert();
    }).toJS;
    picker.click();
  }

  void transformAction(String choice) {
    if (choice == 'drag') {
      setState(() {
        moveOnce = true;
        pan = false;
        status = '拖动画板移动笔迹';
      });
      return;
    }
    final before = revision();
    file.zoomSketch(
      choice == 'in' ? 1.25 : 0.8,
      Offset(file.size.width / 2, file.size.height / 2),
    );
    setState(() {
      remember(before);
      status = null;
    });
  }

  void finish() {
    if (active.isEmpty) return;
    if (recordCursor && file is BlackboardPage) {
      final before = revision();
      try {
        (file as BlackboardPage).appendCursor(
          active,
          touchTimes!,
          cursorColor,
          cursorWidth,
        );
        remember(before);
        status = '光标已追加到本页回放';
      } on FormatException catch (e) {
        status = e.message;
      }
      setState(() {
        active = [];
        touchTimes = null;
      });
      return;
    }
    final straight = shape == PenShape.line && !erasing;
    final times = touchTimes;
    final ink = Ink(
      straight ? [active.first, active.last] : List.of(active),
      color,
      erasing ? math.max(12, width) : width,
      erase: erasing,
      eventTimes: straight && times != null ? [times.first, times.last] : times,
      shape: shape,
      dashed: dashed && file.format == BoardFormat.simple,
    );
    final before = revision();
    if (file.format == BoardFormat.touchSource) {
      if (selected == null) {
        setState(() {
          status = '先点选要重画的笔迹';
          active = [];
        });
        return;
      }
      file.replaceTouch(selected!, ink);
    } else {
      if (file.format == BoardFormat.simple)
        file.simpleCreationRadius = simpleRadiusOnPage;
      file.draw(ink);
    }
    setState(() {
      remember(before);
      active = [];
      status = null;
      selected = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final simpleErasing = file.format == BoardFormat.simple && erasing && !pan;
    final toolWidth = recordCursor
        ? cursorWidth
        : simpleErasing
        ? simpleEraserRadius
        : width;
    final kind = switch (file.format) {
      BoardFormat.sketch => 'Sketch',
      BoardFormat.legacy => 'Sketch V1',
      BoardFormat.simple => 'SimpleBoard',
      BoardFormat.touchSource => 'Blackboard 触摸分片',
      BoardFormat.pageSnapshot => 'Blackboard 页面',
    };
    return Scaffold(
      backgroundColor: const Color(0xffe7eeec),
      body: SafeArea(
        child: Column(
          children: [
            Container(
              color: const Color(0xff173a35),
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              child: Row(
                children: [
                  const Icon(Icons.gesture, color: Color(0xffb7e6d0)),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      '画板编辑器',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 21,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  PopupMenuButton<bool>(
                    tooltip: '新建笔记或页面',
                    icon: const Icon(
                      Icons.note_add_outlined,
                      color: Colors.white,
                    ),
                    onSelected: createPageDocument,
                    itemBuilder: (_) => [
                      const PopupMenuItem(
                        value: false,
                        child: Text('新建 Blackboard 笔记'),
                      ),
                      if (archive?.canAddBlackboardPage == true)
                        const PopupMenuItem(
                          value: true,
                          child: Text('在当前笔记加一页'),
                        ),
                    ],
                  ),
                  TextButton.icon(
                    onPressed: open,
                    icon: const Icon(Icons.folder_open),
                    label: const Text('打开 BIN / ZIP'),
                    style: TextButton.styleFrom(foregroundColor: Colors.white),
                  ),
                  IconButton(
                    tooltip: '打开画板文件夹',
                    onPressed: openDirectory,
                    icon: const Icon(Icons.folder_copy_outlined),
                    color: Colors.white,
                  ),
                  const SizedBox(width: 8),
                  if (archive?.canExportCloudNote == true)
                    IconButton(
                      tooltip: '按页面 BIN 导出云笔记副本',
                      onPressed: () => save(cloudCopy: true),
                      color: Colors.white,
                      icon: const Icon(Icons.file_copy_outlined),
                    ),
                  FilledButton.tonalIcon(
                    onPressed: save,
                    icon: const Icon(Icons.download),
                    label: Text(archive == null ? '导出 BIN' : '导出 ZIP'),
                  ),
                ],
              ),
            ),
            AbsorbPointer(
              absorbing: frame != null,
              child: ExcludeSemantics(
                excluding: frame != null,
                child: Opacity(
                  opacity: frame == null ? 1 : 0.45,
                  child: Material(
                    color: Colors.white,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 4,
                      ),
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            IconButton(
                              isSelected:
                                  !dragImages &&
                                  !recordCursor &&
                                  !recordCamera &&
                                  !erasing &&
                                  !pan &&
                                  shape == PenShape.free,
                              tooltip: '画笔',
                              onPressed: () => setState(() {
                                clearContactState();
                                erasing = false;
                                pan = false;
                                shape = PenShape.free;
                              }),
                              icon: const Icon(Icons.edit_outlined),
                            ),
                            IconButton(
                              isSelected: !dragImages && erasing,
                              tooltip: '橡皮',
                              onPressed: file.format == BoardFormat.touchSource
                                  ? null
                                  : () => setState(() {
                                      clearContactState();
                                      erasing = true;
                                      pan = false;
                                    }),
                              icon: const Icon(Icons.auto_fix_normal),
                            ),
                            IconButton(
                              tooltip: '直线',
                              isSelected:
                                  !dragImages &&
                                  !recordCursor &&
                                  !recordCamera &&
                                  !erasing &&
                                  !pan &&
                                  shape == PenShape.line,
                              onPressed: () => setState(() {
                                clearContactState();
                                shape = PenShape.line;
                                pan = false;
                                erasing = false;
                              }),
                              icon: const Icon(Icons.show_chart),
                            ),
                            if (file.format == BoardFormat.sketch ||
                                file.format == BoardFormat.legacy)
                              for (final choice in [
                                (PenShape.rectangle, '矩形', Icons.crop_square),
                                (PenShape.ellipse, '椭圆', Icons.circle_outlined),
                              ])
                                IconButton(
                                  tooltip: choice.$2,
                                  isSelected:
                                      !erasing && !pan && shape == choice.$1,
                                  onPressed: () => setState(() {
                                    shape = choice.$1;
                                    pan = false;
                                    erasing = false;
                                  }),
                                  icon: Icon(choice.$3),
                                ),
                            if (file.format == BoardFormat.simple)
                              IconButton(
                                tooltip: '虚线',
                                isSelected: dashed,
                                onPressed: () =>
                                    setState(() => dashed = !dashed),
                                icon: const Icon(Icons.more_horiz),
                              ),
                            if (file case final BlackboardPage page)
                              if (page.canRecordCamera)
                                IconButton(
                                  tooltip: '录制页末镜头',
                                  icon: const Icon(Icons.open_with),
                                  isSelected: recordCamera,
                                  onPressed: () => setState(() {
                                    final enable = !recordCamera;
                                    clearContactState();
                                    recordCamera = enable;
                                    erasing = false;
                                    pan = false;
                                    status = enable
                                        ? '拖动画布移动镜头，双指可按本页设置缩放'
                                        : null;
                                  }),
                                ),
                            if (file case final BlackboardPage page)
                              if (page.canRecordCursor)
                                IconButton(
                                  tooltip: '录制页末光标',
                                  icon: const Icon(Icons.adjust),
                                  isSelected: recordCursor,
                                  onPressed: () => setState(() {
                                    final enable = !recordCursor;
                                    clearContactState();
                                    recordCursor = enable;
                                    pan = false;
                                    erasing = false;
                                    status = enable
                                        ? '在画布上移动光标，松开后追加到页末'
                                        : null;
                                  }),
                                ),
                            if (file case final BlackboardPage page)
                              if (page.supportsArtworkEditing)
                                IconButton(
                                  tooltip: '设置纸张',
                                  icon: const Icon(Icons.grid_on_outlined),
                                  onPressed: () async {
                                    final before = revision();
                                    final changed = await showDialog<bool>(
                                      context: context,
                                      builder: (_) => _PaperDialog(page),
                                    );
                                    if (changed == true &&
                                        mounted &&
                                        identical(file, page)) {
                                      setState(() {
                                        remember(before);
                                        frame = null;
                                        status = '已更新本页纸张';
                                      });
                                    }
                                  },
                                ),
                            if (file case final BlackboardPage page)
                              if (archive?.canAddBlackboardPage == true)
                                IconButton(
                                  tooltip: '追加本页录音',
                                  onPressed: page.pageAudio.issue == null
                                      ? () => chooseAudio(page)
                                      : null,
                                  icon: const Icon(
                                    Icons.library_music_outlined,
                                  ),
                                ),
                            if (file case final BlackboardPage page)
                              if (page.supportsArtworkEditing)
                                PopupMenuButton<ArtworkKind>(
                                  tooltip: '插入图元',
                                  icon: const Icon(Icons.add_box_outlined),
                                  onSelected: (kind) {
                                    if (kind == ArtworkKind.image) {
                                      chooseImage();
                                    } else {
                                      insertPageArtwork(page, kind);
                                    }
                                  },
                                  itemBuilder: (_) => [
                                    for (final kind in ArtworkKind.values)
                                      PopupMenuItem(
                                        value: kind,
                                        child: Text(kind.label),
                                      ),
                                  ],
                                ),
                            if (file case final BlackboardPage page)
                              if (page.supportsArtworkEditing &&
                                  page.artwork.any((a) => a.editable))
                                PopupMenuButton<PageArtwork>(
                                  tooltip: '编辑图元',
                                  icon: const Icon(Icons.edit_note),
                                  onSelected: (art) async {
                                    final before = revision();
                                    final changed = await showDialog<bool>(
                                      context: context,
                                      builder: (_) => _ArtworkDialog(page, art),
                                    );
                                    if (changed == true &&
                                        mounted &&
                                        identical(file, page)) {
                                      setState(() {
                                        remember(before);
                                        status = '已更新图元 · ${art.id}';
                                      });
                                    }
                                  },
                                  itemBuilder: (_) => [
                                    for (final a in page.artwork.where(
                                      (a) => a.editable,
                                    ))
                                      PopupMenuItem(
                                        value: a,
                                        child: Text(
                                          a.label,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                  ],
                                ),
                            if (file case final BlackboardPage page)
                              if (page.supportsArtworkEditing &&
                                  page.artwork.any((a) => a.image != null))
                                IconButton(
                                  tooltip: '拖动图片',
                                  icon: const Icon(Icons.open_with),
                                  isSelected: dragImages,
                                  onPressed: () => setState(() {
                                    final enable = !dragImages;
                                    clearContactState();
                                    dragImages = enable;
                                    pan = false;
                                    status = enable ? '拖动页面中的图片' : null;
                                  }),
                                ),
                            if (file.canInsertSketchImage)
                              IconButton(
                                tooltip: '插入图片',
                                icon: const Icon(
                                  Icons.add_photo_alternate_outlined,
                                ),
                                onPressed: chooseImage,
                              ),
                            for (final item in frame?.artwork ?? file.artwork)
                              if (item.presentation case final deck?
                                  when deck.hasHtml)
                                _SlideControls(deck, _slideSession(file, deck)),
                            if (file.canTransformSketch)
                              PopupMenuButton<String>(
                                tooltip: '画板变换',
                                icon: const Icon(Icons.transform),
                                onSelected: transformAction,
                                itemBuilder: (_) => const [
                                  PopupMenuItem(
                                    value: 'drag',
                                    child: Text('移动笔迹（双指或 Shift 拖动）'),
                                  ),
                                  PopupMenuItem(
                                    value: 'in',
                                    child: Text('放大画板 125%'),
                                  ),
                                  PopupMenuItem(
                                    value: 'out',
                                    child: Text('缩小画板至 80%'),
                                  ),
                                ],
                              ),
                            IconButton(
                              tooltip: '平移与缩放',
                              isSelected: pan,
                              onPressed: () => setState(() {
                                clearContactState();
                                pan = !pan;
                              }),
                              icon: const Icon(Icons.open_with),
                            ),
                            IconButton(
                              tooltip: '适应画布',
                              onPressed: () => setState(() {
                                clearContactState();
                                viewport.value = Matrix4.identity();
                                pan = false;
                              }),
                              icon: const Icon(Icons.fit_screen),
                            ),
                            if (archive?.backgroundImage != null)
                              IconButton(
                                tooltip: '设置原生画布宽度',
                                icon: const Icon(Icons.straighten),
                                onPressed: () async {
                                  final owner = archive!;
                                  var value = file.size.width
                                      .round()
                                      .toString();
                                  final width = await showDialog<double>(
                                    context: context,
                                    builder: (context) => AlertDialog(
                                      title: const Text('原生画布宽度（像素）'),
                                      content: TextFormField(
                                        initialValue: value,
                                        keyboardType: TextInputType.number,
                                        onChanged: (v) => value = v,
                                      ),
                                      actions: [
                                        TextButton(
                                          onPressed: () =>
                                              Navigator.pop(context),
                                          child: const Text('取消'),
                                        ),
                                        FilledButton(
                                          onPressed: () {
                                            final width = double.tryParse(
                                              value,
                                            );
                                            if (width != null &&
                                                width.isFinite &&
                                                width > 0)
                                              Navigator.pop(context, width);
                                          },
                                          child: const Text('应用'),
                                        ),
                                      ],
                                    ),
                                  );
                                  if (mounted &&
                                      width != null &&
                                      archive == owner)
                                    setState(() => owner.setSimpleWidth(width));
                                },
                              ),
                            const SizedBox(width: 12),
                            for (final c in [
                              if (recordCursor) 0xffff0000,
                              0xff213836,
                              0xff267162,
                              0xff326eab,
                              0xffbc4c46,
                              0xffae7725,
                            ])
                              Semantics(
                                button: true,
                                label: '笔色 ${c.toRadixString(16)}',
                                child: InkWell(
                                  onTap: () => setState(() {
                                    if (recordCursor) {
                                      cursorColor = c;
                                    } else {
                                      color = c;
                                    }
                                  }),
                                  child: Padding(
                                    padding: const EdgeInsets.all(5),
                                    child: CircleAvatar(
                                      radius: 11,
                                      backgroundColor: Color(c),
                                      child:
                                          (recordCursor
                                                  ? cursorColor
                                                  : color) ==
                                              c
                                          ? const Icon(
                                              Icons.check,
                                              size: 16,
                                              color: Colors.white,
                                            )
                                          : null,
                                    ),
                                  ),
                                ),
                              ),
                            const SizedBox(width: 12),
                            Text(
                              '${simpleErasing ? '橡皮半径 ' : ''}${toolWidth.round()} px',
                            ),
                            SizedBox(
                              width: 115,
                              child: Slider(
                                value: toolWidth,
                                min: 1,
                                max: simpleErasing ? 80 : 24,
                                divisions: simpleErasing ? 79 : 23,
                                onChanged: (v) => setState(() {
                                  if (recordCursor) {
                                    cursorWidth = v;
                                  } else if (simpleErasing) {
                                    simpleEraserRadius = v;
                                  } else {
                                    width = v;
                                  }
                                }),
                              ),
                            ),
                            IconButton(
                              tooltip: '撤销',
                              onPressed: undo.isEmpty
                                  ? null
                                  : () => restore(undo, redo),
                              icon: const Icon(Icons.undo),
                            ),
                            IconButton(
                              tooltip: '重做',
                              onPressed: redo.isEmpty
                                  ? null
                                  : () => restore(redo, undo),
                              icon: const Icon(Icons.redo),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
            if (file.timeline case final SketchTimeline time
                when time.durationMs > 0)
              RecordingControls(
                key: ObjectKey(time),
                timeline: time,
                readAudio: (name) => archive?.sketchAudio(name),
                onPosition: (next, direct) => setState(() {
                  frame = next == null ? null : time.seek(next);
                  clearContactState();
                }),
              ),
            if (file case final BlackboardPage page)
              if (page.pageAudio case final track
                  when track.durationMs > 0 &&
                      (track.clips.isNotEmpty || page.replay.available))
                RecordingControls(
                  key: ObjectKey(track),
                  timeline: track,
                  readAudio: page.audioBytes,
                  onPosition: page.replay.available
                      ? (next, direct) => setState(() {
                          try {
                            frame = next == null
                                ? null
                                : page.replay.seek(next, direct: direct);
                          } on Exception catch (e) {
                            page.replay.issue = '回放资源读取失败 · $e';
                            frame = null;
                          }
                          clearContactState();
                        })
                      : null,
                ),
            if (file case final BlackboardPage page)
              if ((page.pageAudio.issue ?? page.replay.issue)
                  case final String issue)
                Text(issue),
            if (status != null || file.unrendered.isNotEmpty)
              Container(
                width: double.infinity,
                color: scheme.secondaryContainer,
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 6,
                ),
                child: Text(
                  status ?? '已保留、预览暂未显示的操作 · ${file.unrendered.join("、")}',
                ),
              ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Center(
                  child: AspectRatio(
                    aspectRatio: file.size.aspectRatio,
                    child: LayoutBuilder(
                      builder: (context, c) {
                        final scale = c.maxWidth / file.size.width;
                        final visible = frame ?? cameraGesture?.preview;
                        final drawArea = frame == null
                            ? file.sketchDrawArea
                            : frame!.sketchDrawArea;
                        final layer = visible?.cameraInkLayer;
                        final artwork =
                            layer?.artwork ?? visible?.artwork ?? file.artwork;
                        final cursor =
                            frame?.cursor ??
                            (recordCursor &&
                                    active.isNotEmpty &&
                                    file is BlackboardPage
                                ? (file as BlackboardPage).cursorAt(
                                    active.last,
                                    cursorColor,
                                    cursorWidth,
                                  )
                                : null);
                        return InteractiveViewer(
                          transformationController: viewport,
                          panEnabled: pan,
                          scaleEnabled: pan,
                          minScale: 1,
                          maxScale: 8,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: file is BlackboardPage
                                  ? Color.alphaBlend(
                                      Color(
                                        frame?.background ?? file.background,
                                      ),
                                      Colors.white,
                                    )
                                  : Color(frame?.background ?? file.background),
                              boxShadow: const [
                                BoxShadow(
                                  color: Color(0x22000000),
                                  blurRadius: 6,
                                  offset: Offset(0, 2),
                                ),
                              ],
                            ),
                            child: ClipRect(
                              child: Listener(
                                behavior: HitTestBehavior.opaque,
                                onPointerDown: (e) {
                                  if (pan || frame != null) return;
                                  final p = e.localPosition / scale;
                                  if (simpleErasing) {
                                    if (simpleEraserPointer == null) {
                                      simpleEraserPointer = e.pointer;
                                      simpleEraseRemembered = false;
                                      touchSimpleEraser(p);
                                    }
                                    return;
                                  }
                                  if (recordCamera) {
                                    setState(() => startCameraContact(e, p));
                                    return;
                                  }
                                  if (recordCursor) {
                                    contacts[e.pointer] = p;
                                    if (contacts.length > 1 || liftContacts) {
                                      setState(() {
                                        liftContacts = true;
                                        pointer = null;
                                        active = [];
                                        touchTimes = null;
                                      });
                                      return;
                                    }
                                  }
                                  if (dragImages) {
                                    if (imageDrag == null) {
                                      final art = artwork.reversed
                                          .where((a) => a.containsImagePoint(p))
                                          .firstOrNull;
                                      if (art != null)
                                        setState(
                                          () => imageDrag = _ImageDrag(
                                            e.pointer,
                                            art,
                                            p,
                                          ),
                                        );
                                    }
                                    return;
                                  }
                                  if (file case final BlackboardPage page) {
                                    if (!recordCursor &&
                                        !erasing &&
                                        e.kind == ui.PointerDeviceKind.touch &&
                                        page.canRecordCamera &&
                                        beginWritingContact(e, p, page)) {
                                      setState(() {});
                                      return;
                                    }
                                  }
                                  if (file.canTransformSketch) {
                                    if (liftContacts || contacts.length >= 2)
                                      return;
                                    contacts[e.pointer] = p;
                                    if (contacts.length == 2 ||
                                        moveOnce ||
                                        HardwareKeyboard
                                            .instance
                                            .isShiftPressed) {
                                      setState(() {
                                        pointer = null;
                                        active = [];
                                        dragOrigin = contactCenter;
                                        dragDelta = Offset.zero;
                                      });
                                      return;
                                    }
                                  }
                                  if (pointer != null) return;
                                  if (file.format == BoardFormat.touchSource &&
                                      selected == null) {
                                    double d = double.infinity;
                                    int? index;
                                    for (
                                      var i = 0;
                                      i < file.strokes.length;
                                      i++
                                    ) {
                                      for (final q in file.strokes[i].points) {
                                        final dist = (p - q).distance;
                                        if (dist < d) {
                                          d = dist;
                                          index = i;
                                        }
                                      }
                                    }
                                    if (index != null && d * scale < 25)
                                      setState(() {
                                        selected = index;
                                        status =
                                            '已选中第 ${index! + 1} 条笔迹，请在画布上重画';
                                      });
                                    return;
                                  }
                                  setState(() {
                                    pointer = e.pointer;
                                    cursorOffset =
                                        recordCursor &&
                                            e.kind == ui.PointerDeviceKind.touch
                                        ? const Offset(0, -50)
                                        : Offset.zero;
                                    active = [p + cursorOffset];
                                    touchTimes = null;
                                    if (file is BlackboardPage) {
                                      final start =
                                          DateTime.now().millisecondsSinceEpoch;
                                      touchEpoch =
                                          start - e.timeStamp.inMilliseconds;
                                      touchTimes = [start];
                                    }
                                  });
                                },
                                onPointerMove: (e) {
                                  if (simpleEraserPointer == e.pointer) {
                                    touchSimpleEraser(e.localPosition / scale);
                                    return;
                                  }
                                  if (recordCamera || cameraGesture != null) {
                                    if (cameraGesture != null &&
                                        contacts.containsKey(e.pointer)) {
                                      setState(() {
                                        contacts[e.pointer] =
                                            e.localPosition / scale;
                                        cameraGesture!.move(
                                          contactCenter,
                                          contactSpan,
                                          touchEpoch +
                                              e.timeStamp.inMilliseconds,
                                        );
                                      });
                                    }
                                    return;
                                  }
                                  if (dragImages) {
                                    final drag = imageDrag;
                                    if (drag?.pointer == e.pointer)
                                      setState(
                                        () => drag!.delta =
                                            e.localPosition / scale -
                                            drag.start,
                                      );
                                    return;
                                  }
                                  if (contacts.containsKey(e.pointer)) {
                                    contacts[e.pointer] =
                                        e.localPosition / scale;
                                    if (dragOrigin != null) {
                                      setState(
                                        () => dragDelta =
                                            contactCenter - dragOrigin!,
                                      );
                                      return;
                                    }
                                  }
                                  if (pointer == e.pointer)
                                    setState(() {
                                      active.add(
                                        e.localPosition / scale + cursorOffset,
                                      );
                                      touchTimes?.add(
                                        touchEpoch + e.timeStamp.inMilliseconds,
                                      );
                                    });
                                },
                                onPointerUp: (e) {
                                  if (simpleEraserPointer == e.pointer) {
                                    touchSimpleEraser(
                                      e.localPosition / scale,
                                      lifted: true,
                                    );
                                    return;
                                  }
                                  if (recordCamera || cameraGesture != null) {
                                    if (cameraGesture?.writing == true &&
                                        contacts.containsKey(e.pointer)) {
                                      contacts[e.pointer] =
                                          e.localPosition / scale;
                                      cameraGesture!.move(
                                        contactCenter,
                                        null,
                                        touchEpoch + e.timeStamp.inMilliseconds,
                                      );
                                    }
                                    setState(
                                      () => endCameraContact(
                                        e.pointer,
                                        cancelled: false,
                                      ),
                                    );
                                    return;
                                  }
                                  if (dragImages) {
                                    if (imageDrag?.pointer == e.pointer)
                                      finishImageDrag(e.localPosition / scale);
                                    return;
                                  }
                                  if (contacts.containsKey(e.pointer) &&
                                      dragOrigin != null) {
                                    contacts[e.pointer] =
                                        e.localPosition / scale;
                                    dragDelta = contactCenter - dragOrigin!;
                                  }
                                  if (endBoardDrag(e.pointer, cancelled: false))
                                    return;
                                  if (pointer == e.pointer) {
                                    active.add(
                                      e.localPosition / scale + cursorOffset,
                                    );
                                    touchTimes?.add(
                                      touchEpoch + e.timeStamp.inMilliseconds,
                                    );
                                    pointer = null;
                                    finish();
                                  }
                                },
                                onPointerCancel: (e) {
                                  if (simpleEraserPointer == e.pointer) {
                                    setState(() {
                                      simpleEraserPointer = null;
                                      simpleEraserTip = null;
                                    });
                                    return;
                                  }
                                  if (recordCamera || cameraGesture != null) {
                                    setState(
                                      () => endCameraContact(
                                        e.pointer,
                                        cancelled: true,
                                      ),
                                    );
                                    return;
                                  }
                                  if (dragImages) {
                                    if (imageDrag?.pointer == e.pointer)
                                      setState(() => imageDrag = null);
                                    return;
                                  }
                                  if (endBoardDrag(e.pointer, cancelled: true))
                                    return;
                                  if (pointer == e.pointer)
                                    setState(() {
                                      pointer = null;
                                      active = [];
                                    });
                                },
                                child: ClipRect(
                                  clipper: drawArea == null || drawArea.isEmpty
                                      ? null
                                      : _SketchAreaClipper(drawArea, scale),
                                  child: Stack(
                                    fit: StackFit.expand,
                                    children: [
                                      if (file case final BlackboardPage page)
                                        CustomPaint(
                                          painter: _LivePaperPainter(
                                            visible?.paperLines ??
                                                page.paperLines,
                                            visible?.paperCamera ?? page.camera,
                                            scale,
                                          ),
                                        ),
                                      if (archive?.backgroundImage
                                          case final Uint8List image)
                                        Image.memory(image, fit: BoxFit.fill),
                                      _CameraInkView(
                                        layer?.delta,
                                        scale,
                                        child: Stack(
                                          fit: StackFit.expand,
                                          children: [
                                            if (artwork.isNotEmpty)
                                              ...pageLayers(
                                                file,
                                                artwork,
                                                scale,
                                                layer?.strokes ??
                                                    visible?.strokes,
                                                dragDelta,
                                                draggedImage: imageDrag,
                                              ),
                                            CustomPaint(
                                              painter: InkPainter(
                                                file,
                                                recordCursor
                                                    ? const []
                                                    : active,
                                                color,
                                                width,
                                                erasing,
                                                selected,
                                                shape,
                                                dashed,
                                                shift: dragDelta,
                                                simpleEraserTip:
                                                    simpleEraserTip,
                                                simpleEraserRadius:
                                                    simpleRadiusOnPage,
                                                visible:
                                                    layer?.strokes ??
                                                    visible?.strokes,
                                                start:
                                                    artwork
                                                        .lastOrNull
                                                        ?.beforeStroke ??
                                                    0,
                                              ),
                                              size: Size.infinite,
                                            ),
                                          ],
                                        ),
                                      ),
                                      if (cursor != null)
                                        CustomPaint(
                                          painter: _CursorPainter(
                                            cursor,
                                            scale,
                                          ),
                                        ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
              ),
            ),
            Container(
              color: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
              child: Row(
                children: [
                  if (archive != null && archive!.entries.length > 1)
                    DropdownButton<int>(
                      value: archive!.index,
                      items: [
                        for (var i = 0; i < archive!.entries.length; i++)
                          DropdownMenuItem(
                            value: i,
                            child: Text('第 ${i + 1} 页'),
                          ),
                      ],
                      onChanged: (i) {
                        if (i == null) return;
                        setState(() {
                          archive!.select(i);
                          file = archive!.current;
                          clearContactState();
                          frame = null;
                          undo.clear();
                          redo.clear();
                          active = [];
                          selected = null;
                          status = null;
                        });
                      },
                    ),
                  Expanded(
                    child: Text(
                      file.hasThumbnailBacking
                          ? '${file.name}   ·   $kind · JPEG 底图，导出时合并笔迹'
                          : '${file.name}   ·   $kind',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(
                    '${file.hasThumbnailBacking ? '新增 ' : ''}${frame?.strokes.length ?? file.strokes.length} 笔    ${file.size.width.round()} × ${file.size.height.round()}',
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class InkPainter extends CustomPainter {
  InkPainter(
    this.file,
    this.active,
    this.color,
    this.width,
    this.erase,
    this.selected,
    this.shape,
    this.dashed, {
    this.visible,
    this.simpleEraserTip,
    this.simpleEraserRadius = 0,
    this.shift = Offset.zero,
    this.start = 0,
    this.end,
    this.layerSize,
  });
  final List<Ink>? visible;
  final Offset? simpleEraserTip;
  final double simpleEraserRadius;
  final Offset shift;
  final int start;
  final int? end;
  final Size? layerSize;
  final BoardFile file;
  final List<Offset> active;
  final int color;
  final double width;
  final bool erase;
  final int? selected;
  final PenShape shape;
  final bool dashed;
  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / file.size.width);
    canvas.saveLayer(Offset.zero & (layerSize ?? file.size), Paint());
    canvas.translate(shift.dx, shift.dy);
    final sketch =
        file.format == BoardFormat.sketch || file.format == BoardFormat.legacy;
    void line(Ink ink, bool highlight) {
      final pts = ink.points;
      if (pts.isEmpty) return;
      final paint = Paint()
        ..color = highlight ? Colors.orange : Color(ink.argb)
        ..strokeWidth = ink.width.clamp(0.25, 256).toDouble()
        ..strokeCap = sketch ? StrokeCap.butt : StrokeCap.round
        ..strokeJoin = sketch ? StrokeJoin.miter : StrokeJoin.round
        ..style = PaintingStyle.stroke;
      if (ink.erase) paint.blendMode = BlendMode.clear;
      if (pts.length == 1 || pts.every((p) => p == pts.first)) {
        if (ink.boardPaint?.style == 0 && !ink.unfinishedPath && pts.length > 1)
          return;
        paint.style = PaintingStyle.fill;
        if (sketch) {
          if (pts.length == 1)
            canvas.drawRect(
              Rect.fromCenter(
                center: pts.first,
                width: paint.strokeWidth,
                height: paint.strokeWidth,
              ),
              paint,
            );
        } else {
          canvas.drawCircle(pts.first, paint.strokeWidth / 2, paint);
        }
        return;
      }
      if (ink.shape == PenShape.rectangle || ink.shape == PenShape.ellipse) {
        final bounds = Rect.fromPoints(pts.first, pts.last);
        if (ink.shape == PenShape.rectangle) {
          canvas.drawRect(bounds, paint);
        } else {
          canvas.drawOval(bounds, paint);
        }
        return;
      }
      if (ink.shape == PenShape.line && !ink.dashed) {
        canvas.drawLine(pts.first, pts.last, paint);
        return;
      }
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (var i = 1; i < pts.length; i++) {
        final p = pts[i], prev = pts[i - 1];
        // Sketch compares PointF values, even in the middle of a stroke.
        if (sketch && p == pts.first) {
          path.moveTo(p.dx, p.dy);
          path.lineTo(p.dx, p.dy);
          continue;
        }
        // DrawControl uses the previous point as a quadratic control point.
        if (file.format == BoardFormat.simple ||
            sketch ||
            file.format == BoardFormat.pageSnapshot ||
            file.format == BoardFormat.touchSource) {
          path.quadraticBezierTo(
            prev.dx,
            prev.dy,
            (p.dx + prev.dx) / 2,
            (p.dy + prev.dy) / 2,
          );
          if ((sketch ? p == pts.last : i == pts.length - 1) &&
              !ink.unfinishedPath)
            path.lineTo(p.dx, p.dy);
        } else {
          path.lineTo(p.dx, p.dy);
        }
      }
      final native = ink.boardPaint;
      if (native != null && native.style != 1) {
        paint.style = PaintingStyle.fill;
        canvas.drawPath(path, paint);
        if (native.style == 0) return;
        paint.style = PaintingStyle.stroke;
      }
      if (!ink.dashed &&
          !(native != null && native.spacing > 0 && native.itemLength > 0)) {
        canvas.drawPath(path, paint);
        return;
      }
      for (final m in path.computeMetrics()) {
        final length = native?.itemLength ?? 30.0,
            gap = native?.spacing ?? 15.0;
        for (double i = 0; i < m.length; i += length + gap) {
          canvas.drawPath(m.extractPath(i, i + length), paint);
        }
      }
    }

    final strokes = visible ?? file.strokes;
    for (var i = start; i < (end ?? strokes.length); i++) {
      line(strokes[i], i == selected);
    }
    line(
      Ink(active, color, width, erase: erase, shape: shape, dashed: dashed),
      false,
    );
    if (simpleEraserTip case final tip?) {
      canvas.drawCircle(
        tip,
        simpleEraserRadius,
        Paint()..color = const Color(0xffff0000),
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(InkPainter oldDelegate) => true;
}
