part of 'main.dart';

Future<({int width, int flag})?> _placeImage(
  BuildContext context,
  Size image,
  Size board,
) {
  final fit = math.min(
    1.0,
    math.min(board.width / image.width, board.height / image.height),
  );
  var width = math.max(1, (image.width * fit).round());
  var flag = 0;
  const positions = {
    1: '左上',
    2: '上方居中',
    3: '右上',
    4: '左侧居中',
    0: '居中',
    6: '右侧居中',
    7: '左下',
    8: '下方居中',
    9: '右下',
  };
  return showDialog<({int width, int flag})>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, update) => AlertDialog(
        title: const Text('插入图片'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              initialValue: width.toString(),
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '显示宽度（画布像素）'),
              onChanged: (text) =>
                  update(() => width = int.tryParse(text) ?? 0),
            ),
            DropdownButton<int>(
              value: flag,
              isExpanded: true,
              items: [
                for (final option in positions.entries)
                  DropdownMenuItem(
                    value: option.key,
                    child: Text(option.value),
                  ),
              ],
              onChanged: (value) {
                if (value != null) update(() => flag = value);
              },
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed:
                width > 0 &&
                    width <= 2147483647 &&
                    width / image.aspectRatio <= 2147483647
                ? () => Navigator.pop(ctx, (width: width, flag: flag))
                : null,
            child: const Text('插入'),
          ),
        ],
      ),
    ),
  );
}
