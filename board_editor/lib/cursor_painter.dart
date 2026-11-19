part of 'main.dart';

class _CursorPainter extends CustomPainter {
  _CursorPainter(this.cursor, this.scale);
  final PageCursor cursor;
  final double scale;

  @override
  void paint(Canvas canvas, Size size) {
    final brush = cursor.brush, radius = cursor.localRadius;
    if (!radius.isFinite || radius <= 0) return;
    final circle = Path()
      ..addOval(Rect.fromCircle(center: cursor.local, radius: radius));
    final path = circle.transform(_canvasTransform(cursor.camera, 1).storage);
    final paint = Paint()
      ..color = Color(brush.color)
      ..strokeWidth = brush.width
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.scale(scale);
    if (brush.style != 1) canvas.drawPath(path, paint);
    if (brush.style != 0) {
      paint.style = PaintingStyle.stroke;
      if (brush.spacing > 0 && brush.itemLength > 0) {
        for (final m in path.computeMetrics()) {
          for (
            var i = 0.0;
            i < m.length;
            i += brush.spacing + brush.itemLength
          ) {
            canvas.drawPath(m.extractPath(i, i + brush.itemLength), paint);
          }
        }
      } else {
        canvas.drawPath(path, paint);
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_CursorPainter old) =>
      old.cursor != cursor || old.scale != scale;
}
