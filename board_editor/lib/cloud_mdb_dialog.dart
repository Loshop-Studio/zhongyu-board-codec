part of 'main.dart';

class _CloudInkScreen extends StatefulWidget {
  const _CloudInkScreen(
    this.files, {
    required this.hasBin,
    this.archive,
    this.original,
    this.name,
  });
  final List<ArchiveFile> files;
  final bool hasBin;
  final Archive? archive;
  final Uint8List? original;
  final String? name;
  @override
  State<_CloudInkScreen> createState() => _CloudInkScreenState();
}

class _CloudInkScreenState extends State<_CloudInkScreen> {
  final opened = <String, CloudInkDocument>{};
  int fileIndex = 0, pageIndex = 0;
  int? selected, dragged, pointer;
  Offset? tip;
  bool handles = false;
  CloudInkDocument? document;
  String? error;
  ArchiveFile get file => widget.files[fileIndex];
  @override
  void initState() {
    super.initState();
    load();
  }

  void load() {
    selected = null;
    dragged = null;
    tip = null;
    handles = false;
    error = null;
    document = null;
    try {
      final d = opened.putIfAbsent(
        file.name,
        () => CloudInkDocument(
          file.content,
          member: file.name,
          archive: widget.archive,
        ),
      );
      if (d.pages.isNotEmpty) d.openPage(pageIndex);
      document = d;
    } catch (e) {
      error = '打开页面失败 · $e';
    }
  }

  void action(VoidCallback change) {
    try {
      change();
      document!.openPage(pageIndex);
      setState(() {});
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  void exportZip() {
    final orig = widget.original;
    if (orig != null && opened.values.every((d) => !d.canUndo)) {
      _download(widget.name!, orig);
      return;
    }
    final out = Archive();
    for (final item in widget.archive!) {
      final updated = opened[item.name];
      out.addFile(
        updated != null && updated.canUndo
            ? ArchiveFile.bytes(item.name, updated.store.bytes)
            : item,
      );
    }
    _download(widget.name!, ZipEncoder().encodeBytes(out));
  }

  void selectAt(Offset point, double scale) {
    final strokes = document!.board.strokes;
    int? hit;
    var best = double.infinity;
    for (int i = strokes.length - 1; i >= 0; i--) {
      final ink = strokes[i];
      for (var j = 0; j < ink.points.length; j++) {
        final a = ink.points[j == 0 ? 0 : j - 1],
            b = ink.points[j],
            delta = b - a;
        final t = delta.distanceSquared == 0
            ? 0.0
            : (((point.dx - a.dx) * delta.dx + (point.dy - a.dy) * delta.dy) /
                      delta.distanceSquared)
                  .clamp(0.0, 1.0);
        final distance = (point - (a + delta * t)).distance;
        if (distance <= 8 / scale + ink.width / 2 && distance < best) {
          best = distance;
          hit = i;
        }
      }
    }
    setState(() => selected = hit);
  }

  void details(CloudInkDocument d) {
    final rows = d.store.rows['TextInfoEntity']!;
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('数据库详情'),
        content: SizedBox(
          width: 480,
          height: 350,
          child: ListView(
            children: [
              SelectableText(file.name),
              Text(
                '${d.pages.length} 页 · ${d.store.counts.length} 种实体 · ${d.store.counts.values.fold(0, (a, b) => a + b)} 条记录',
              ),
              for (final p in d.pages)
                Text(p.string('dirName') ?? '页面 ${p.id}'),
              for (final row in rows.values) Text(row.string('content') ?? ''),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final d = document;
    final hasPage = d != null && d.pages.isNotEmpty;
    final board = hasPage ? d.board : null;
    return Scaffold(
      backgroundColor: const Color(0xffe7eeec),
      appBar: AppBar(
        title: const Text('MDB 笔迹画板'),
        actions: [
          if (d != null)
            IconButton(
              tooltip: '数据库详情',
              icon: const Icon(Icons.info_outline),
              onPressed: () => details(d),
            ),
          if (widget.hasBin)
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('打开旧 BIN 页面'),
            ),
          if (d != null)
            TextButton.icon(
              onPressed: () =>
                  _download(file.name.split('/').last, d.store.bytes),
              icon: const Icon(Icons.download),
              label: const Text('导出 MDB'),
            ),
          if (widget.archive != null)
            TextButton(onPressed: exportZip, child: const Text('导出 ZIP')),
        ],
      ),
      body: Column(
        children: [
          Material(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  const SizedBox(width: 12),
                  if (widget.files.length > 1)
                    DropdownButton<int>(
                      value: fileIndex,
                      items: [
                        for (int i = 0; i < widget.files.length; i++)
                          DropdownMenuItem(
                            value: i,
                            child: Text(widget.files[i].name),
                          ),
                      ],
                      onChanged: (i) => setState(() {
                        fileIndex = i!;
                        pageIndex = 0;
                        load();
                      }),
                    ),
                  if (hasPage)
                    DropdownButton<int>(
                      value: pageIndex,
                      items: [
                        for (int i = 0; i < d.pages.length; i++)
                          DropdownMenuItem(
                            value: i,
                            child: Text(
                              '第 ${i + 1} 页 · ${d.pages[i].string('dirName') ?? ''}',
                            ),
                          ),
                      ],
                      onChanged: (i) => setState(() {
                        pageIndex = i!;
                        load();
                      }),
                    ),
                  if (board != null && board.strokes.isNotEmpty)
                    DropdownButton<int>(
                      hint: const Text('选择笔迹'),
                      value: selected,
                      items: [
                        for (int i = 0; i < board.strokes.length; i++)
                          DropdownMenuItem(
                            value: i,
                            child: Text('第 ${i + 1} 笔'),
                          ),
                      ],
                      onChanged: (i) => setState(() => selected = i),
                    ),
                  for (final c in const [
                    (0xff202020, '黑色'),
                    (0xffd32f2f, '红色'),
                    (0xff1565c0, '蓝色'),
                    (0xff228451, '绿色'),
                  ])
                    IconButton(
                      tooltip: c.$2,
                      icon: Icon(Icons.circle, color: Color(c.$1)),
                      onPressed: selected == null
                          ? null
                          : () => action(() => d!.edit(selected!, color: c.$1)),
                    ),
                  PopupMenuButton<double>(
                    tooltip: '线宽',
                    enabled: selected != null,
                    icon: const Icon(Icons.line_weight),
                    onSelected: (w) =>
                        action(() => d!.edit(selected!, width: w)),
                    itemBuilder: (_) => [
                      for (final w in const [1, 3, 6, 9, 12, 18])
                        PopupMenuItem(
                          value: w.toDouble(),
                          child: Text('$w px'),
                        ),
                    ],
                  ),
                  IconButton(
                    tooltip: '调整采样点',
                    isSelected: handles,
                    icon: const Icon(Icons.polyline_outlined),
                    onPressed: selected == null
                        ? null
                        : () => setState(() => handles = !handles),
                  ),
                  TextButton(
                    onPressed: selected == null
                        ? null
                        : () => action(() => d!.edit(selected!, smooth: true)),
                    child: const Text('平滑笔迹'),
                  ),
                  IconButton(
                    tooltip: '撤销',
                    onPressed: d?.canUndo == true
                        ? () => action(d!.undo)
                        : null,
                    icon: const Icon(Icons.undo),
                  ),
                  IconButton(
                    tooltip: '重做',
                    onPressed: d?.canRedo == true
                        ? () => action(d!.redo)
                        : null,
                    icon: const Icon(Icons.redo),
                  ),
                ],
              ),
            ),
          ),
          if (board != null)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Center(
                  child: AspectRatio(
                    aspectRatio: board.size.aspectRatio,
                    child: LayoutBuilder(
                      builder: (context, box) {
                        final scale = box.maxWidth / board.size.width;
                        return Semantics(
                          container: true,
                          identifier: 'cloud-ink-canvas',
                          label: 'MDB 笔迹画布',
                          child: Listener(
                            behavior: HitTestBehavior.opaque,
                            onPointerDown: (e) {
                              if (pointer != null) return;
                              pointer = e.pointer;
                              final pos = e.localPosition / scale;
                              if (!handles || selected == null) {
                                selectAt(pos, scale);
                                return;
                              }
                              final points = board.strokes[selected!].points;
                              double nearest = 14 / scale;
                              int? hit;
                              for (int i = 0; i < points.length; i++) {
                                final distance = (pos - points[i]).distance;
                                if (distance <= nearest) {
                                  nearest = distance;
                                  hit = i;
                                }
                              }
                              setState(() {
                                dragged = hit;
                                tip = hit == null ? null : points[hit];
                              });
                            },
                            onPointerMove: (e) {
                              if (e.pointer == pointer && dragged != null)
                                setState(() => tip = e.localPosition / scale);
                            },
                            onPointerCancel: (e) {
                              if (e.pointer == pointer)
                                setState(() {
                                  pointer = null;
                                  dragged = null;
                                  tip = null;
                                });
                            },
                            onPointerUp: (e) {
                              if (e.pointer != pointer) return;
                              pointer = null;
                              final index = dragged;
                              if (index == null) return;
                              setState(() {
                                dragged = null;
                                tip = null;
                              });
                              action(
                                () => d!.edit(
                                  selected!,
                                  movePoint: (index, e.localPosition / scale),
                                ),
                              );
                            },
                            child: ClipRect(
                              child: ColoredBox(
                                color: Color(board.background).a == 0
                                    ? Colors.white
                                    : Color(board.background),
                                child: CustomPaint(
                                  painter: _LivePaperPainter(
                                    board.paperLines,
                                    board.camera,
                                    scale,
                                  ),
                                  foregroundPainter: selected == null
                                      ? null
                                      : _InkOutline(
                                          board.strokes[selected!],
                                          scale,
                                          handles,
                                          dragged,
                                          tip,
                                        ),
                                  child: Stack(
                                    fit: StackFit.expand,
                                    children: [
                                      ...pageLayers(
                                        board,
                                        board.artwork,
                                        scale,
                                        null,
                                        Offset.zero,
                                      ),
                                      CustomPaint(
                                        painter: InkPainter(
                                          board,
                                          const [],
                                          0,
                                          1,
                                          false,
                                          null,
                                          PenShape.free,
                                          false,
                                          start:
                                              board
                                                  .artwork
                                                  .lastOrNull
                                                  ?.beforeStroke ??
                                              0,
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
          if (board != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                '${board.strokes.length} 笔 · ${board.size.width.round()} × ${board.size.height.round()}'
                '${selected == null ? '' : ' · 已选第 ${selected! + 1} 笔'}${d!.notice == null ? '' : ' · ${d.notice}'}',
              ),
            ),
          if (!hasPage)
            Expanded(child: Center(child: Text(error ?? '此数据库没有页面'))),
        ],
      ),
    );
  }
}

class _InkOutline extends CustomPainter {
  const _InkOutline(
    this.stroke,
    this.scale,
    this.handles,
    this.dragged,
    this.tip,
  );
  final bool handles;
  final int? dragged;
  final Offset? tip;
  final Ink stroke;
  final double scale;
  @override
  void paint(Canvas canvas, Size size) {
    if (stroke.points.isEmpty) return;
    var bounds = Rect.fromPoints(stroke.points.first, stroke.points.first);
    for (final p in stroke.points) {
      bounds = bounds.expandToInclude(Rect.fromPoints(p, p));
    }
    canvas.scale(scale);
    if (handles) {
      final brush = Paint()..color = const Color(0xff148876);
      for (final p in stroke.points) canvas.drawCircle(p, 3 / scale, brush);
      if (dragged != null && tip != null) {
        final i = dragged!;
        final path = Path();
        final a = stroke.points[i == 0 ? 0 : i - 1],
            b = stroke.points[i + 1 < stroke.points.length ? i + 1 : i];
        path.moveTo(a.dx, a.dy);
        path.lineTo(tip!.dx, tip!.dy);
        path.lineTo(b.dx, b.dy);
        canvas.drawCircle(tip!, 5 / scale, brush);
        canvas.drawPath(
          path,
          brush
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1 / scale,
        );
      }
    }
    canvas.drawRect(
      bounds.inflate(stroke.width / 2 + 3 / scale),
      Paint()
        ..color = const Color(0xff148876)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1 / scale,
    );
  }

  @override
  bool shouldRepaint(_InkOutline old) => true;
}
