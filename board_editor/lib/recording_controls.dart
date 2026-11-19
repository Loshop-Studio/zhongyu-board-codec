part of 'main.dart';

class RecordingControls extends StatefulWidget {
  const RecordingControls({
    super.key,
    required this.timeline,
    required this.readAudio,
    this.onPosition,
  });
  final RecordingTrack timeline;
  final Uint8List? Function(String) readAudio;
  final void Function(int? position, bool direct)? onPosition;
  @override
  State<RecordingControls> createState() => _RecordingControlsState();
}

class _RecordingControlsState extends State<RecordingControls> {
  final clock = Stopwatch();
  Timer? timer;
  int position = 0, origin = 0;
  bool preview = false, audioOnly = false;
  bool get showFrames => widget.onPosition != null && !audioOnly;
  void toggleFrames() {
    audioOnly = !audioOnly;
    widget.onPosition?.call(showFrames && preview ? position : null, true);
    setState(() {});
  }

  RecordingClip? clip;
  web.HTMLAudioElement? audio;
  String? url, soundIssue;
  int get duration => widget.timeline.durationMs;

  void releaseAudio() {
    audio?.pause();
    if (url != null) web.URL.revokeObjectURL(url!);
    clip = null;
    audio = null;
    url = null;
    soundIssue = null;
  }

  void playAudio(web.HTMLAudioElement player) {
    player.play().toDart.catchError((Object e) {
      if (mounted && audio == player && clock.isRunning) {
        setState(() => soundIssue = '浏览器未能播放音轨');
      }
      return null;
    });
  }

  void syncAudio({required bool seeking}) {
    final next = widget.timeline.clipAt(position);
    final changed = next != clip;
    if (changed) {
      releaseAudio();
      clip = next;
      if (next == null) return;
      final bytes = widget.readAudio(next.filename);
      if (bytes == null) {
        soundIssue = '缺少音轨 ${next.filename}';
        return;
      }
      final mime = switch (next.filename.toLowerCase().split('.').last) {
        'wav' => 'audio/wav',
        'mp3' => 'audio/mpeg',
        'm4a' || 'mp4' => 'audio/mp4',
        'ogg' || 'opus' => 'audio/ogg',
        'aac' => 'audio/aac',
        _ => '',
      };
      url = web.URL.createObjectURL(
        web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: mime)),
      );
      audio = web.HTMLAudioElement()
        ..preload = 'auto'
        ..src = url!;
    }
    final player = audio;
    if (next == null || player == null) return;
    final offset = (position - next.startMs) / 1000;
    if (changed ||
        seeking ||
        (player.readyState >= 2 &&
            !player.paused &&
            (player.currentTime - offset).abs() > 0.22)) {
      player.currentTime = offset;
    }
    if (clock.isRunning && (changed || seeking)) playAudio(player);
    if (!clock.isRunning) player.pause();
  }

  void show(int value, {bool seeking = false, bool direct = false}) {
    position = value.clamp(0, duration);
    preview = true;
    syncAudio(seeking: seeking);
    if (showFrames) widget.onPosition?.call(position, direct);
    setState(() {});
  }

  void pause() {
    timer?.cancel();
    timer = null;
    clock.stop();
    audio?.pause();
  }

  void play() {
    if (clock.isRunning) {
      pause();
      setState(() {});
      return;
    }
    origin = position >= duration ? 0 : position;
    clock
      ..reset()
      ..start();
    show(origin, seeking: true);
    timer = Timer.periodic(const Duration(milliseconds: 24), (_) {
      final time = origin + clock.elapsedMilliseconds;
      if (time >= duration) pause();
      show(time);
    });
  }

  void seek(double value) {
    origin = value.round();
    clock.reset();
    show(origin, seeking: true, direct: true);
  }

  void edit() {
    pause();
    releaseAudio();
    position = 0;
    preview = false;
    widget.onPosition?.call(null, true);
    setState(() {});
  }

  @override
  void dispose() {
    pause();
    releaseAudio();
    super.dispose();
  }

  String stamp(int time) =>
      '${time ~/ 60000}:${((time ~/ 1000) % 60).toString().padLeft(2, "0")}.${((time ~/ 10) % 100).toString().padLeft(2, "0")}';
  @override
  Widget build(BuildContext context) => Material(
    color: Colors.white,
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          IconButton(
            tooltip: !showFrames
                ? (clock.isRunning ? '暂停本页录音' : '播放本页录音')
                : (clock.isRunning
                      ? '暂停回放'
                      : widget.timeline is BlackboardAudioTrack
                      ? '播放本页回放'
                      : '播放录制'),
            onPressed: play,
            icon: Icon(clock.isRunning ? Icons.pause : Icons.play_arrow),
          ),
          Text('${stamp(position)} / ${stamp(duration)}'),
          Expanded(
            child: Semantics(
              label: !showFrames ? '本页录音进度' : '回放进度',
              child: Slider(
                value: position.toDouble(),
                max: duration.toDouble(),
                semanticFormatterCallback: (v) => stamp(v.round()),
                onChanged: seek,
              ),
            ),
          ),
          if (widget.timeline is BlackboardAudioTrack &&
              widget.onPosition != null &&
              widget.timeline.clips.isNotEmpty)
            IconButton(
              tooltip: audioOnly ? '同步回放画面' : '只听录音',
              icon: Icon(audioOnly ? Icons.slideshow : Icons.headphones),
              onPressed: toggleFrames,
            ),
          if (soundIssue != null)
            Tooltip(message: soundIssue!, child: const Icon(Icons.volume_off)),
          if (preview)
            TextButton(
              onPressed: edit,
              child: Text(!showFrames ? '停止试听' : '返回编辑'),
            ),
        ],
      ),
    ),
  );
}
