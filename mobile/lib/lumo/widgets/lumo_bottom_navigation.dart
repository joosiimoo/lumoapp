import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';

enum LumoTab { inicio, hoy, memoria, negocio }

class LumoBottomNavigation extends StatelessWidget {
  const LumoBottomNavigation({
    super.key,
    required this.current,
    required this.onSelect,
  });

  final LumoTab current;
  final ValueChanged<LumoTab> onSelect;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: LumoColors.background.withValues(alpha: 0.95),
        border: Border(top: BorderSide(color: LumoColors.border.withValues(alpha: 0.6))),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _item(LumoTab.inicio, 'Inicio', Icons.home_outlined),
              _item(LumoTab.hoy, 'Hoy', Icons.calendar_today_outlined),
              _item(LumoTab.memoria, 'Memoria', Icons.auto_awesome),
              _item(LumoTab.negocio, 'Negocio', Icons.storefront_outlined),
            ],
          ),
        ),
      ),
    );
  }

  Widget _item(LumoTab tab, String label, IconData icon) {
    final selected = current == tab;
    return GestureDetector(
      onTap: () => onSelect(tab),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedContainer(
            duration: LumoMotion.duration,
            curve: LumoMotion.curve,
            width: LumoSizes.navPillWidth,
            height: LumoSizes.navPillHeight,
            decoration: BoxDecoration(
              color: selected ? LumoColors.accent : Colors.transparent,
              borderRadius: BorderRadius.circular(LumoRadius.pill),
            ),
            child: Icon(
              icon,
              size: LumoSizes.navIcon,
              color: selected ? LumoColors.foreground : LumoColors.mutedForeground,
            ),
          ),
          const SizedBox(height: 4),
          Text(label, style: selected ? LumoTypography.navLabelActive : LumoTypography.navLabel),
        ],
      ),
    );
  }
}
