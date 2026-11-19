part of 'main.dart';

Future<int> _audioDuration(web.File file) async {
  final audio = web.HTMLAudioElement();
  final ready = Completer<int>();
  final url = web.URL.createObjectURL(file);
  audio.onloadedmetadata = ((web.Event _) {
    final seconds = audio.duration;
    if (ready.isCompleted) return;
    if (seconds.isFinite && seconds > 0) {
      ready.complete((seconds * 1000).round());
    } else {
      ready.completeError(const FormatException('无法确定录音时长'));
    }
  }).toJS;
  audio.onerror = ((web.Event _) {
    if (!ready.isCompleted)
      ready.completeError(const FormatException('浏览器无法解码该音频'));
  }).toJS;
  try {
    audio.preload = 'metadata';
    audio.src = url;
    return await ready.future.timeout(const Duration(seconds: 15));
  } finally {
    audio.onloadedmetadata = null;
    audio.onerror = null;
    audio.removeAttribute('src');
    audio.load();
    web.URL.revokeObjectURL(url);
  }
}

Future<int?> _audioGap(BuildContext context, String name, int duration) {
  int? gap = 0;
  return showDialog<int>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, update) => AlertDialog(
        title: const Text('追加本页录音'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('$name · ${(duration / 1000).toStringAsFixed(2)} 秒'),
            TextFormField(
              initialValue: '0',
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '页末静音间隔（毫秒）'),
              onChanged: (v) => update(() => gap = int.tryParse(v)),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: gap != null && gap! >= 0 && gap! <= 2147483647
                ? () => Navigator.pop(ctx, gap)
                : null,
            child: const Text('追加'),
          ),
        ],
      ),
    ),
  );
}
