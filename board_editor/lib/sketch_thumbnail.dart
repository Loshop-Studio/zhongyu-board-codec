part of 'main.dart';

/// DrawView clips the displayed ink and images in view coordinates.
class _SketchAreaClipper extends CustomClipper<Rect> {
  const _SketchAreaClipper(this.area, this.scale);
  final Rect area;
  final double scale;
  @override
  Rect getClip(Size size) => Rect.fromLTRB(
    area.left * scale,
    area.top * scale,
    area.right * scale,
    area.bottom * scale,
  ).intersect(Offset.zero & size);
  @override
  bool shouldReclip(_SketchAreaClipper old) =>
      old.area != area || old.scale != scale;
}

/// Rebuild the recorder's JPEG from the final graph, independent of the
/// selection, playback position and interactive zoom level in the editor.
Future<Uint8List> _sketchThumbnail(BoardFile file, Uint8List? original) async {
  if (file.sketchUsesThumbnailAsSource && !file.hasThumbnailBacking) {
    throw const FormatException('旧画板缺少可作为底图的静态 JPEG');
  }
  if (file.unrendered.isNotEmpty) {
    throw FormatException(file.unrendered.join('，'));
  }
  if (file.artwork.any((art) => art.presentation != null)) {
    throw const FormatException('课件预览需要原生 WebView 画面');
  }
  final width = file.size.width.toInt(), height = file.size.height.toInt();
  if (width <= 0 ||
      height <= 0 ||
      width * height > BoardArchive.maxMemberBytes ~/ 4) {
    throw const FormatException('预览尺寸超出可用像素范围');
  }
  if (original != null && !file.hasThumbnailBacking) {
    final info = raster.JpegDecoder().startDecode(original);
    if (info == null || info.width != width || info.height != height) {
      throw const FormatException('来源 JPEG 尺寸与画板文件头不同');
    }
  }
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  final images = <ui.Image>[];
  ui.Picture? picture;
  try {
    canvas.drawColor(Color(file.background), BlendMode.src);
    if (file.sketchPreviewClip case final Rect clip) {
      canvas.clipRect(clip, doAntiAlias: false);
    }
    var start = 0;
    void inkThrough(int end) {
      if (end <= start) return;
      InkPainter(
        file,
        const [],
        0,
        1,
        false,
        null,
        PenShape.free,
        false,
        start: start,
        end: end,
      ).paint(canvas, file.size);
      start = end;
    }

    for (final art in file.artwork) {
      inkThrough(art.beforeStroke);
      final bitmap = art.sketchBitmap;
      if (bitmap == null) throw const FormatException('未识别的 Sketch 图元');
      final codec = await ui.instantiateImageCodec(bitmap.bytes);
      try {
        final image = (await codec.getNextFrame()).image;
        images.add(image);
        canvas.save();
        canvas.transform(
          _canvasTransform(
            bitmap.displayMatrix(art.transform, image.width.toDouble()),
            1,
          ).storage,
        );
        canvas.drawImage(
          image,
          Offset.zero,
          Paint()
            ..filterQuality = FilterQuality.low
            ..color = Color.fromRGBO(255, 255, 255, bitmap.opacity),
        );
        canvas.restore();
      } finally {
        codec.dispose();
      }
    }
    inkThrough(file.strokes.length);
    picture = recorder.endRecording();
    final image = await picture.toImage(width, height);
    try {
      // Android's ARGB bitmap compressor ignores alpha in the premultiplied
      // color. Black behind transparent pixels gives the same RGB input.
      final rgba = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (rgba == null) throw StateError('JPEG 像素读取失败');
      final rgb = raster.Image.fromBytes(
        width: width,
        height: height,
        bytes: rgba.buffer,
        bytesOffset: rgba.offsetInBytes,
        numChannels: 4,
      ).convert(numChannels: 3);
      return raster.encodeJpg(
        rgb,
        quality: 70,
        chroma: raster.JpegChroma.yuv420,
      );
    } finally {
      image.dispose();
    }
  } finally {
    (picture ?? recorder.endRecording()).dispose();
    for (final image in images) {
      image.dispose();
    }
  }
}
