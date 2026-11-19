part of 'main.dart';

/// PageControl.save draws the persisted camera and graph into an ARGB bitmap.
/// The toolbar's zoom, selection and current replay position are view state.
Future<Uint8List> _pagePreview(BlackboardPage page) async {
  if (page.unrendered.isNotEmpty) {
    throw FormatException(page.unrendered.join('，'));
  }
  final meta = page.previewHeader;
  final move = meta.moveConfig;
  final viewport = Offset.zero & page.size;
  var crop = viewport;
  if (move.isEnable) {
    final area = Rect.fromLTWH(
      0,
      0,
      page.size.width * move.maxWidthTimes,
      page.size.height * move.maxHeightTimes,
    );
    final mapped = MatrixUtils.transformRect(
      _canvasTransform(page.camera, 1),
      area,
    );
    if (viewport.overlaps(mapped)) crop = viewport.intersect(mapped);
  }
  var content = false;
  var width = crop.width.toInt() + 1;
  var height = crop.height.toInt() + 1;
  final path = '${page.dir}screenshot.png';
  if (page.bundle.has(path)) {
    final bytes = page.bundle.read(path);
    final header = ByteData.sublistView(bytes);
    if (bytes.length < 33 ||
        header.getUint32(0) != 0x89504e47 ||
        header.getUint32(4) != 0x0d0a1a0a ||
        header.getUint32(12) != 0x49484452) {
      throw const FormatException('来源预览没有 PNG 文件头');
    }
    final w = header.getUint32(16), h = header.getUint32(20);
    final viewportHeight = page.size.height.toInt();
    final contentWidth =
        page.size.width.toInt() * (move.isEnable ? move.maxWidthTimes : 1);
    final maxHeight =
        viewportHeight * (move.isEnable ? move.maxHeightTimes : 1);
    // Content thumbnails ignore the saved camera and use the graph bounds to
    // crop the bottom of the scrollable area, with one viewport as the minimum.
    if (header.getUint8(25) == 2 &&
        w == contentWidth &&
        h >= viewportHeight &&
        h <= maxHeight) {
      content = true;
      width = w;
      page.refresh(applyCamera: false);
      height = move.isEnable
          ? page.contentBottom.clamp(viewportHeight, maxHeight).toInt()
          : viewportHeight;
    } else if (w != width || h != height || header.getUint8(25) != 6) {
      throw const FormatException('来源预览尺寸或编码与页面截图不同');
    }
  }
  if (width <= 0 ||
      height <= 0 ||
      width * height > BoardArchive.maxMemberBytes ~/ 4) {
    throw const FormatException('预览尺寸超出可用像素范围');
  }
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  final images = <ui.Image>[];
  ui.Picture? picture;
  try {
    if (content) canvas.drawColor(const Color(0xff000000), BlendMode.src);
    canvas.drawColor(Color(page.background), BlendMode.srcOver);
    if (page.paperLines.lineColor != 0) {
      final matrix = content
          ? Matrix4.identity()
          : _canvasTransform(page.camera, 1);
      final inverse = Matrix4.tryInvert(matrix);
      if (inverse == null) throw const FormatException('背景坐标矩阵不可逆');
      final bounds = MatrixUtils.transformRect(
        inverse,
        Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
      );
      final grid = _paperPath(
        page.paperLines,
        bounds,
        page.paperLines.lineSpace,
      );
      if (grid == null) throw const FormatException('背景线间距超出可绘制范围');
      canvas.drawPath(
        grid.transform(matrix.storage),
        _paperPen(page.paperLines),
      );
    }
    var start = 0;
    void inkThrough(int end) {
      if (start == end) return;
      InkPainter(
        page,
        const [],
        0,
        1,
        false,
        null,
        PenShape.free,
        false,
        start: start,
        end: end,
        layerSize: Size(width.toDouble(), height.toDouble()),
      ).paint(canvas, page.size);
      start = end;
    }

    for (final art in page.artwork) {
      inkThrough(art.beforeStroke);
      final matrix = _canvasTransform(art.transform, 1);
      if (art.image case final Uint8List bytes) {
        final codec = await ui.instantiateImageCodec(bytes);
        try {
          final image = (await codec.getNextFrame()).image;
          images.add(image);
          final src = Rect.fromLTWH(
            0,
            0,
            image.width.toDouble(),
            image.height.toDouble(),
          );
          final dest = Rect.fromLTWH(
            0,
            0,
            art.bounds.width,
            art.bounds.width * image.height / image.width,
          );
          canvas.save();
          canvas.transform(matrix.storage);
          canvas.drawImageRect(
            image,
            src,
            dest,
            Paint()..filterQuality = FilterQuality.none,
          );
          canvas.restore();
        } finally {
          codec.dispose();
        }
      } else {
        _ArtworkPainter(art, matrix).paint(canvas, page.size);
      }
    }
    inkThrough(page.strokes.length);
    picture = recorder.endRecording();
    final result = await picture.toImage(width, height);
    try {
      if (content) return await _rgb565Png(result);
      final bytes = await result.toByteData(format: ui.ImageByteFormat.png);
      if (bytes == null) throw StateError('PNG 编码失败');
      return bytes.buffer.asUint8List(bytes.offsetInBytes, bytes.lengthInBytes);
    } finally {
      result.dispose();
    }
  } finally {
    (picture ?? recorder.endRecording()).dispose();
    for (final image in images) {
      image.dispose();
    }
  }
}

Future<Uint8List> _rgb565Png(ui.Image image) async {
  final rgba = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  if (rgba == null) throw StateError('RGB 像素读取失败');
  final rgb = Uint8List(image.width * image.height * 3);
  for (int i = 0, j = 0; j < rgb.length; i += 4) {
    final r = rgba.getUint8(i) >> 3;
    final g = rgba.getUint8(i + 1) >> 2;
    final b = rgba.getUint8(i + 2) >> 3;
    rgb[j++] = (r << 3) | (r >> 2);
    rgb[j++] = (g << 2) | (g >> 4);
    rgb[j++] = (b << 3) | (b >> 2);
  }
  return raster.encodePng(
    raster.Image.fromBytes(
      width: image.width,
      height: image.height,
      bytes: rgb.buffer,
      numChannels: 3,
    ),
  );
}
