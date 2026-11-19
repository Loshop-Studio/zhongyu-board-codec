part of 'main.dart';

typedef _ArtworkDraft = ({Rect area, String content, double penSize});

class _CreateArtworkDialog extends StatefulWidget {
  const _CreateArtworkDialog(this.kind, this.board, this.image, this.brush);
  final ArtworkKind kind;
  final Size board;
  final Size? image;
  final double brush;
  @override
  State<_CreateArtworkDialog> createState() => _CreateArtworkDialogState();
}

class _CreateArtworkDialogState extends State<_CreateArtworkDialog> {
  final fields = <String, TextEditingController>{};
  String? error;
  bool get isText => widget.kind == ArtworkKind.text;
  @override
  void initState() {
    super.initState();
    final board = widget.board, image = widget.image;
    final w = image == null
        ? board.width * (isText ? .4 : .2)
        : math.max(
            1.0,
            math.min(
              image.width,
              math.min(board.width, board.height * image.aspectRatio),
            ),
          );
    final h = image == null
        ? (isText ? math.min(80.0, board.height) : board.height * .2)
        : w / image.aspectRatio;
    final values = {
      if (isText) '文字内容': '',
      '页面 X': ((board.width - w) / 2).round().toString(),
      '页面 Y': ((board.height - h) / 2).round().toString(),
      '图元宽度': w.round().toString(),
      if (image == null) '图元高度': h.round().toString(),
      if (isText) '字号': '28',
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

  void apply() {
    try {
      double value(String key) {
        final n = double.tryParse(fields[key]!.text.trim());
        if (n == null || !n.isFinite || n.abs() > 2147483647) {
          throw FormatException('$key 需要有效数值');
        }
        return n;
      }

      final w = value('图元宽度'),
          h = widget.image == null
              ? value('图元高度')
              : w / widget.image!.aspectRatio;
      final size = isText ? value('字号') : widget.brush;
      final content = fields['文字内容']?.text ?? '';
      if (w <= 0 ||
          h <= 0 ||
          size <= 0 ||
          (widget.image != null && (w < 1 || h < 1))) {
        throw const FormatException('图元尺寸和画笔大小必须大于零');
      }
      if (isText && content.trim().isEmpty)
        throw const FormatException('请输入文字');
      final rect = Rect.fromLTWH(value('页面 X'), value('页面 Y'), w, h);
      Navigator.pop(context, (area: rect, content: content, penSize: size));
    } on FormatException catch (e) {
      setState(() => error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text('插入${widget.kind.label}'),
    content: SizedBox(
      width: 320,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final field in fields.entries)
              TextField(
                controller: field.value,
                maxLines: field.key == '文字内容' ? null : 1,
                decoration: InputDecoration(labelText: field.key),
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
      FilledButton(onPressed: apply, child: const Text('插入')),
    ],
  );
}
