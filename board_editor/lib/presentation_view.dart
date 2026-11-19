part of 'main.dart';

@JS('zyMountSlides')
external void _mountSlides(
  web.HTMLIFrameElement frame,
  JSString entry,
  JSFunction read,
  JSFunction report,
);
@JS('zyUnmountSlides')
external void _unmountSlides(web.HTMLIFrameElement frame);
@JS('zyControlSlides')
external void _controlSlides(
  web.HTMLIFrameElement frame,
  JSString command,
  JSNumber page,
);

final _presentations = Expando<Map<String, _SlideSession>>();
_SlideSession _slideSession(BoardFile board, SketchPresentation deck) =>
    (_presentations[board] ??= <String, _SlideSession>{}).putIfAbsent(
      '${deck.id}/${deck.filename}',
      _SlideSession.new,
    );

class _SlideSession {
  web.HTMLIFrameElement? frame;
  final count = ValueNotifier<(int, int)>((0, 0));
  void send(String command, [int page = 0]) {
    if (frame case final target?)
      _controlSlides(target, command.toJS, page.toJS);
  }
}

class _PresentationView extends StatefulWidget {
  const _PresentationView(this.deck, this.session);
  final SketchPresentation deck;
  final _SlideSession session;
  @override
  State<_PresentationView> createState() => _PresentationViewState();
}

class _PresentationViewState extends State<_PresentationView> {
  web.HTMLIFrameElement? iframe;
  @override
  void dispose() {
    if (iframe case final target?) {
      _unmountSlides(target);
      if (widget.session.frame == target) widget.session.frame = null;
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => HtmlElementView.fromTagName(
    tagName: 'iframe',
    onElementCreated: (Object element) {
      final target = element as web.HTMLIFrameElement;
      final deck = widget.deck, session = widget.session;
      iframe = target;
      session.frame = target;
      _mountSlides(
        target,
        deck.filename.toJS,
        ((JSString path) => deck.resource(path.toDart)?.toJS).toJS,
        ((JSNumber current, JSNumber total) {
          if (mounted && session.frame == target)
            session.count.value = (current.toDartInt, total.toDartInt);
        }).toJS,
      );
    },
  );
}

class _SlideControls extends StatelessWidget {
  const _SlideControls(this.deck, this.session);
  final SketchPresentation deck;
  final _SlideSession session;
  @override
  Widget build(BuildContext context) => PopupMenuButton<String>(
    tooltip: '课件控制 · ${deck.filename}',
    icon: const Icon(Icons.slideshow_outlined),
    onSelected: (op) async {
      if (op != 'GotoSlide') {
        session.send(op);
        return;
      }
      int? page;
      final selected = await showDialog<int>(
        context: context,
        builder: (ctx) => StatefulBuilder(
          builder: (ctx, update) => AlertDialog(
            title: const Text('跳至课件页'),
            content: TextField(
              autofocus: true,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '课件页码'),
              onChanged: (s) => update(() => page = int.tryParse(s)),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: page != null && page! >= 0 && page! <= 2147483647
                    ? () => Navigator.pop(ctx, page)
                    : null,
                child: const Text('跳转'),
              ),
            ],
          ),
        ),
      );
      if (selected != null) session.send(op, selected);
    },
    itemBuilder: (_) => [
      PopupMenuItem<String>(
        enabled: false,
        child: ValueListenableBuilder<(int, int)>(
          valueListenable: session.count,
          builder: (_, v, child) => Text(
            v.$2 > 0 ? '${deck.filename} · ${v.$1} / ${v.$2}' : deck.filename,
          ),
        ),
      ),
      for (final item in const {
        'Prev': '上一步动画',
        'Next': '下一步动画',
        'PrvSlide': '上一张幻灯片',
        'NxtSlide': '下一张幻灯片',
        'GotoSlide': '跳至课件页',
      }.entries)
        PopupMenuItem(value: item.key, child: Text(item.value)),
    ],
  );
}
