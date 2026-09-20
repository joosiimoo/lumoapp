import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lumo/lumo/tokens.dart';

void main() {
  test('design tokens match the approved identity', () {
    expect(LumoColors.background, const Color(0xFFFCFAF4));
    expect(LumoColors.surface, const Color(0xFFFCFAF4));
    expect(LumoColors.surfaceElevated, const Color(0xFFFFFFFF));
    expect(LumoColors.foreground, const Color(0xFF0A140E));
    expect(LumoColors.mutedForeground, const Color(0xFF5C675D));
    expect(LumoColors.primary, const Color(0xFF267B4C));
    expect(LumoColors.primaryForeground, const Color(0xFFFCFAF4));
    expect(LumoColors.secondary, const Color(0xFFF1F3EB));
    expect(LumoColors.accent, const Color(0xFFDAF2E6));
    expect(LumoColors.border, const Color(0xFFE3E6DE));
    expect(LumoColors.destructive, const Color(0xFFDE3B3D));
    expect(LumoColors.user, const Color(0xFF267B4C));
    expect(LumoColors.attention, const Color(0xFFD79628));
    expect(LumoColors.lumoTeal, const Color(0xFF78D7D6));
    expect(LumoColors.lumoLavender, const Color(0xFFB1B0EF));
    expect(LumoColors.markCore, const Color(0xFF042C43));
    expect(LumoGradients.lumoText, const [
      Color(0xFF36BABA),
      Color(0xFF5EADE2),
      Color(0xFFAE96DA),
    ]);
    expect(LumoSizes.contentMaxWidth, 420);
    expect(LumoRadius.card, 24);
    expect(LumoRadius.userBubble, 28);
    expect(LumoMotion.duration, const Duration(milliseconds: 150));
  });
}
