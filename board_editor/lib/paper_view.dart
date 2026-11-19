part of 'main.dart';

Paint _paperPen(wire.BackgroundLineConfig lines) => Paint()
  ..color = Color(lines.lineColor)
  ..style = PaintingStyle.stroke
  ..strokeWidth = lines.lineWidth
  ..strokeCap = StrokeCap.round
  ..strokeJoin = StrokeJoin.round;

Path? _paperPath(wire.BackgroundLineConfig lines, Rect bounds, double step) {
  if (!bounds.isFinite ||
      !step.isFinite ||
      step <= 0 ||
      (bounds.width + bounds.height) / step > 1000000)
    return null;
  final path = Path();
  final nx = (bounds.width / step).truncate() + 3;
  final ny = (bounds.height / step).truncate() + 3;
  for (var i = 0; i < ny; i++) {
    final y = bounds.top + i * step;
    path.moveTo(bounds.left, y);
    path.lineTo(bounds.left + nx * step, y);
  }
  if (lines.lineType.value == 1) {
    for (var i = 0; i < nx; i++) {
      final x = bounds.left + i * step;
      path.moveTo(x, bounds.top);
      path.lineTo(x, bounds.top + ny * step);
    }
  }
  return path;
}

/// BackgroundView.onDraw shifts a screen-aligned grid by the camera origin.
/// Its bitmap export has a different origin (see DrawControl.screenshot).
class _LivePaperPainter extends CustomPainter {
  _LivePaperPainter(this.lines, this.camera, this.scale);
  final wire.BackgroundLineConfig lines;
  final List<double> camera;
  final double scale;

  @override
  void paint(Canvas canvas, Size size) {
    if (lines.lineColor == 0) return;
    final step = lines.lineSpace * camera[0];
    if (!step.isFinite || step <= 0) return;
    final origin = MatrixUtils.transformPoint(
      _canvasTransform(camera, 1),
      Offset.zero,
    );
    final bounds = Rect.fromLTWH(
      origin.dx % step - step,
      origin.dy % step - step,
      size.width / scale,
      size.height / scale,
    );
    final grid = _paperPath(lines, bounds, step);
    if (grid == null) return;
    canvas.save();
    canvas.scale(scale);
    canvas.drawPath(grid, _paperPen(lines));
    canvas.restore();
  }

  @override
  bool shouldRepaint(_LivePaperPainter old) =>
      lines != old.lines || camera != old.camera || scale != old.scale;
}
