import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';

class LumoCard extends StatelessWidget {
  const LumoCard({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: LumoColors.surfaceElevated,
        borderRadius: BorderRadius.all(Radius.circular(LumoRadius.card)),
        boxShadow: LumoShadows.softCard,
      ),
      padding: padding ?? const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: child,
    );
  }
}
