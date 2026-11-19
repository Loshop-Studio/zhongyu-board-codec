part of 'main.dart';

class _PaperDialog extends StatefulWidget {
  const _PaperDialog(this.page);
  final BlackboardPage page;
  @override
  State<_PaperDialog> createState() => _PaperDialogState();
}

class _PaperDialogState extends State<_PaperDialog> {
  late var ruling = widget.page.ruling;
  late final background = TextEditingController(
    text: hex(widget.page.background),
  );
  late final ink = TextEditingController(
    text: hex(
      widget.page.paperLines.lineColor == 0
          ? 0xff557c82
          : widget.page.paperLines.lineColor,
    ),
  );
  late final spacing = TextEditingController(
    text: widget.page.paperLines.lineSpace > 0
        ? '${widget.page.paperLines.lineSpace}'
        : '32',
  );
  String? error;

  String hex(int argb) =>
      argb.toUnsigned(32).toRadixString(16).padLeft(8, '0').toUpperCase();
  int color(TextEditingController controller) {
    final value = controller.text.trim();
    if (!RegExp(r'^[0-9a-fA-F]{8}$').hasMatch(value)) {
      throw const FormatException('颜色需要 8 位 ARGB 十六进制值');
    }
    return int.parse(value, radix: 16);
  }

  void apply() {
    try {
      final ruled = ruling != PaperRuling.plain;
      final changed = widget.page.setPaper(
        color: color(background),
        ruling: ruling,
        lineColor: ruled ? color(ink) : 0,
        spacing: ruled ? double.tryParse(spacing.text.trim()) ?? double.nan : 0,
      );
      Navigator.pop(context, changed);
    } on FormatException catch (e) {
      setState(() => error = e.message);
    }
  }

  @override
  void dispose() {
    background.dispose();
    ink.dispose();
    spacing.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('设置本页纸张'),
      content: SizedBox(
        width: 300,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SegmentedButton<PaperRuling>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: PaperRuling.plain, label: Text('空白')),
                  ButtonSegment(
                    value: PaperRuling.horizontal,
                    label: Text('横线'),
                  ),
                  ButtonSegment(value: PaperRuling.grid, label: Text('方格')),
                ],
                selected: {ruling},
                onSelectionChanged: (value) =>
                    setState(() => ruling = value.single),
              ),
              TextField(
                controller: background,
                decoration: const InputDecoration(labelText: '纸张颜色（ARGB）'),
              ),
              if (ruling != PaperRuling.plain) ...[
                TextField(
                  controller: ink,
                  decoration: const InputDecoration(labelText: '线条颜色（ARGB）'),
                ),
                TextField(
                  controller: spacing,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(labelText: '线距（页面像素）'),
                ),
              ],
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
}
