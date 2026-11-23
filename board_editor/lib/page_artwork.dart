part of 'main.dart';

/// Place non-stroke nodes between the same siblings as in the Android graph.
List<Widget> pageLayers(
  BoardFile page,
  List<PageArtwork> artwork,
  double scale,
  List<Ink>? visible,
  Offset shift, {
  _ImageDrag? draggedImage,
}) {
  var first = 0;
  final result = <Widget>[];
  for (final art in artwork) {
    if (first < art.beforeStroke) {
      result.add(
        CustomPaint(
          painter: InkPainter(
            page,
            const [],
            0,
            1,
            false,
            null,
            PenShape.free,
            false,
            visible: visible,
            shift: shift,
            start: first,
            end: art.beforeStroke,
          ),
        ),
      );
    }
    first = art.beforeStroke;
    if (art.presentation case final deck?) {
      if (deck.hasHtml &&
          deck.width > 0 &&
          deck.height > 0 &&
          deck.opacity > 0) {
        final session = _slideSession(page, deck);
        final matrix = _canvasTransform(art.transform, scale)
          ..multiply(
            Matrix4.diagonal3Values(deck.width / 720, deck.height / 450, 1),
          );
        result.add(
          Positioned(
            key: ObjectKey(session),
            left: shift.dx * scale,
            top: shift.dy * scale,
            child: Transform(
              transform: matrix,
              alignment: Alignment.topLeft,
              child: Opacity(
                opacity: deck.opacity,
                child: SizedBox(
                  width: 720,
                  height: 450,
                  child: _PresentationView(deck, session),
                ),
              ),
            ),
          ),
        );
      }
      continue;
    }
    if (art.sketchBitmap case final SketchBitmap bitmap) {
      result.add(
        Positioned(
          left: shift.dx * scale,
          top: shift.dy * scale,
          child: _SketchImageView(bitmap, art.transform, scale),
        ),
      );
      continue;
    }
    final transform = _canvasTransform(art.transform, scale);
    if (art.imageName != null || art.image != null) {
      final bytes = art.image;
      final offset = identical(draggedImage?.art, art)
          ? draggedImage!.delta
          : Offset.zero;
      result.add(
        Positioned(
          left: offset.dx * scale,
          top: offset.dy * scale,
          child: Transform(
            transform: transform,
            child: bytes == null
                ? SizedBox(
                    width: art.bounds.width,
                    height: art.bounds.height,
                    child: const ColoredBox(
                      color: Color(0xffeeeeee),
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Icon(Icons.broken_image_outlined),
                      ),
                    ),
                  )
                : Image.memory(
                    bytes,
                    width: art.bounds.width,
                    fit: BoxFit.fitWidth,
                    // The V6 ImageGraph renderer draws its bitmap tiles without a filter.
                    filterQuality: FilterQuality.none,
                    errorBuilder: (_, _, _) => const Text('图片解码失败'),
                  ),
          ),
        ),
      );
    } else {
      result.add(CustomPaint(painter: _ArtworkPainter(art, transform)));
    }
  }
  return result;
}

Matrix4 _canvasTransform(List<double> m, double scale) => Matrix4.fromList([
  m[0] * scale,
  m[3] * scale,
  0,
  m[6],
  m[1] * scale,
  m[4] * scale,
  0,
  m[7],
  0,
  0,
  1,
  0,
  m[2] * scale,
  m[5] * scale,
  0,
  m[8],
]);

final _sketchImageSizes = Expando<Future<Size>>();

Future<Size> _encodedSize(Uint8List bytes) async {
  final url = web.URL.createObjectURL(web.Blob([bytes.toJS].toJS));
  try {
    final image = web.HTMLImageElement()..src = url;
    await image.decode().toDart;
    return Size(image.naturalWidth.toDouble(), image.naturalHeight.toDouble());
  } finally {
    web.URL.revokeObjectURL(url);
  }
}

class _SketchImageView extends StatelessWidget {
  const _SketchImageView(this.bitmap, this.root, this.scale);
  final SketchBitmap bitmap;
  final List<double> root;
  final double scale;

  @override
  Widget build(BuildContext context) {
    final bytes = bitmap.bytes;
    return FutureBuilder<Size>(
      key: ObjectKey(bytes),
      future: _sketchImageSizes[bytes] ??= _encodedSize(bytes),
      builder: (context, measured) {
        if (measured.hasError) return Text('图片解码失败 · ${bitmap.filename}');
        final size = measured.data;
        if (size == null) return const SizedBox.shrink();
        final matrix = bitmap.displayMatrix(root, size.width);
        return Transform(
          transform: _canvasTransform(matrix, scale),
          child: Opacity(
            opacity: bitmap.opacity,
            child: Image.memory(
              bytes,
              semanticLabel: bitmap.filename,
              width: size.width,
              height: size.height,
              fit: BoxFit.fill,
              filterQuality: FilterQuality.low,
            ),
          ),
        );
      },
    );
  }
}

/// Android TextGraphUtils counts fitting characters, even inside a word.
/// The original TextGraph advances baselines by Roboto's top-to-bottom
/// font bounds (2163 above and 555 below the baseline per 2048 units).
void _drawPageText(Canvas canvas, PageArtwork art, String content) {
  final size = art.style.textSize;
  final width = art.bounds.width;
  if (size <= 0 || width <= 0 || content.isEmpty) return;
  final style = TextStyle(
    fontFamily: 'Board Android',
    fontFamilyFallback: const ['Board Document'],
    fontSize: size,
    color: Color(art.style.color),
    letterSpacing: 0,
  );
  final painter = TextPainter(textDirection: TextDirection.ltr, maxLines: 1);
  var baseline = size * 2163 / 2048;
  for (final paragraph in content.split('\n')) {
    // Boundaries are UTF-16 offsets. Keep a supplementary character together
    // at a wrap point so the web canvas never paints half a surrogate pair.
    final offsets = [0];
    for (final rune in paragraph.runes) {
      offsets.add(offsets.last + (rune > 0xffff ? 2 : 1));
    }
    for (var start = 0; start < offsets.length - 1;) {
      final remaining = offsets.length - 1 - start;
      void layout(int count) {
        painter.text = TextSpan(
          text: paragraph.substring(offsets[start], offsets[start + count]),
          style: style,
        );
        painter.layout();
      }

      var low = 1, high = 1;
      while (high < remaining) {
        layout(high);
        if (painter.width >= width) break;
        low = high;
        high = math.min(remaining, high * 2);
      }
      while (low < high) {
        final middle = (low + high + 1) ~/ 2;
        layout(middle);
        if (painter.width < width) {
          low = middle;
        } else {
          high = middle - 1;
        }
      }
      layout(low);
      painter.paint(
        canvas,
        Offset(
          0,
          baseline -
              painter.computeDistanceToActualBaseline(TextBaseline.alphabetic),
        ),
      );
      baseline += size * (2163 + 555) / 2048;
      start += low;
    }
  }
  painter.dispose();
}

class _ArtworkPainter extends CustomPainter {
  _ArtworkPainter(this.art, this.matrix);
  final PageArtwork art;
  final Matrix4 matrix;
  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.transform(matrix.storage);
    if (art.text case final String content) {
      _drawPageText(canvas, art, content);
    } else if (art.polygon case final List<Offset> points) {
      final path = Path();
      if (art.oval) {
        path.addOval(art.bounds);
      } else if (points.isNotEmpty) {
        path.addPolygon(points, true);
      }
      final pen = Paint()
        ..color = Color(art.style.color)
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round
        ..strokeWidth = art.style.width;
      if (art.style.style != 1) canvas.drawPath(path, pen);
      if (art.style.style != 0) {
        pen.style = PaintingStyle.stroke;
        final on = art.style.itemLength, off = art.style.spacing;
        if (on > 0 && off > 0) {
          for (final segment in path.computeMetrics()) {
            for (double i = 0; i < segment.length; i += on + off) {
              canvas.drawPath(segment.extractPath(i, i + on), pen);
            }
          }
        } else {
          canvas.drawPath(path, pen);
        }
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_ArtworkPainter oldDelegate) =>
      art != oldDelegate.art || oldDelegate.matrix != matrix;
}
