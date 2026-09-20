import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';

class LumoChip extends StatelessWidget {
  const LumoChip({super.key, required this.label, this.selected = false, this.onTap});

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: LumoMotion.duration,
      curve: LumoMotion.curve,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: selected ? LumoColors.primary : LumoColors.surfaceElevated,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
        border: Border.all(color: selected ? LumoColors.primary : LumoColors.border),
      ),
      child: GestureDetector(
        onTap: onTap,
        child: Text(
          label,
          style: LumoTypography.chip.copyWith(
            color: selected ? LumoColors.primaryForeground : LumoColors.foreground.withValues(alpha: 0.8),
          ),
        ),
      ),
    );
  }
}

class LumoStatusChip extends StatelessWidget {
  const LumoStatusChip({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(
        color: LumoColors.accent,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
      ),
      child: Text(
        label,
        style: LumoTypography.statusChip,
      ),
    );
  }
}
