import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';

class LumoMark extends StatelessWidget {
  const LumoMark({super.key, this.size = LumoSizes.markMd});

  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          Opacity(
            opacity: 0.6,
            child: ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
              child: Container(
                width: size,
                height: size,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    center: Alignment(-0.4, -0.4),
                    radius: 0.65,
                    colors: [Color(0xE676E2E2), Color(0x0076E2E2)],
                  ),
                ),
              ),
            ),
          ),
          CustomPaint(size: Size.square(size), painter: _LumoMarkPainter()),
        ],
      ),
    );
  }
}

class _LumoMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final side = size.shortestSide;
    final center = Offset(size.width / 2, size.height / 2);
    final ring = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: LumoGradients.markRing,
      ).createShader(Offset.zero & size)
      ..style = PaintingStyle.stroke
      ..strokeWidth = side * 2 / 24;
    canvas.drawCircle(center, side * 9.5 / 24, ring);
    final core = Paint()..color = LumoColors.markCore;
    canvas.drawCircle(center, side * 4.5 / 24, core);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
