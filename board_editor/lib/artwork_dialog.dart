part of 'main.dart';

class _ArtworkDialog extends StatefulWidget {
  const _ArtworkDialog(this.page, this.art);
  final BlackboardPage page;
  final PageArtwork art;
  @override
  State<_ArtworkDialog> createState() => _ArtworkDialogState();
}

class _ArtworkDialogState extends State<_ArtworkDialog> {
  final fields = <String, TextEditingController>{};
  late int paintStyle;
  String? error;
  bool get isText => widget.art.text != null;
  bool get isImage => widget.art.image != null;

  @override
  void initState() {
    super.initState();
    final a = widget.art;
    paintStyle = a.style.style;
    final values = {
      if (isImage) ...{
        '缩放比例（%）': '100',
        '顺时针旋转（度）': '0',
      } else ...{
        if (isText) '文字内容': a.text!,
        '颜色（ARGB）': a.style.color
            .toUnsigned(32)
            .toRadixString(16)
            .padLeft(8, '0')
            .toUpperCase(),
        if (isText) '字号': '${a.style.textSize}' else '描边宽度': '${a.style.width}',
        if (a.oval || isText) '图元宽度': '${a.bounds.width}',
        if (a.oval || isText) '图元高度': '${a.bounds.height}',
        if (!a.oval && !isText)
          '顶点（每行 x,y）': a.polygon!.map((p) => '${p.dx},${p.dy}').join('\n'),
      },
      '水平移动': '0',
      '垂直移动': '0',
    };
    values.forEach((k, v) => fields[k] = TextEditingController(text: v));
  }

  @override
  void dispose() {
    for (final c in fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  String value(String key) => fields[key]!.text;
  double number(String key) => double.tryParse(value(key).trim()) ?? double.nan;
  void apply() {
    try {
      final move = Offset(number('水平移动'), number('垂直移动'));
      if (isImage) {
        final changed = widget.page.transformImage(
          widget.art,
          move: move,
          scale: number('缩放比例（%）') / 100,
          degrees: number('顺时针旋转（度）'),
        );
        Navigator.pop(context, changed);
        return;
      }
      final hex = value('颜色（ARGB）').trim().replaceFirst(RegExp('^#'), '');
      if (!RegExp(r'^[a-fA-F0-9]{8}$').hasMatch(hex))
        throw const FormatException('颜色需要 8 位十六进制 ARGB');
      final vertices = fields.containsKey('顶点（每行 x,y）')
          ? value('顶点（每行 x,y）').trim().split('\n').map((line) {
              final xy = line.trim().split(',');
              if (xy.length != 2) throw const FormatException('每行需要一对 x,y 坐标');
              return Offset(
                double.parse(xy.first.trim()),
                double.parse(xy.last.trim()),
              );
            }).toList()
          : null;
      Size? extent;
      if (fields.containsKey('图元宽度')) {
        final proposed = Size(number('图元宽度'), number('图元高度'));
        if (proposed != widget.art.bounds.size) extent = proposed;
      }
      final changed = widget.page.editArtwork(
        widget.art,
        content: isText ? value('文字内容') : null,
        argb: int.parse(hex, radix: 16),
        size: number(isText ? '字号' : '描边宽度'),
        style: isText ? null : paintStyle,
        extent: extent,
        vertices: vertices,
        move: move,
      );
      Navigator.pop(context, changed);
    } on FormatException catch (e) {
      setState(() => error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(isImage ? widget.art.label : '编辑图元 · ${widget.art.id}'),
    content: SizedBox(
      width: 360,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final item in fields.entries)
              TextField(
                controller: item.value,
                maxLines: item.key.startsWith('顶点') || item.key == '文字内容'
                    ? null
                    : 1,
                decoration: InputDecoration(labelText: item.key),
              ),
            if (!isText && !isImage)
              DropdownButtonFormField<int>(
                initialValue: paintStyle >= 0 && paintStyle <= 2
                    ? paintStyle
                    : null,
                decoration: const InputDecoration(labelText: '几何样式'),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('填充')),
                  DropdownMenuItem(value: 1, child: Text('描边')),
                  DropdownMenuItem(value: 2, child: Text('填充及描边')),
                ],
                onChanged: (v) {
                  if (v != null) setState(() => paintStyle = v);
                },
              ),
            if (error != null)
              Text(
                error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('取消'),
      ),
      FilledButton(onPressed: apply, child: const Text('应用')),
    ],
  );
}
