import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';

class LumoPrimaryButton extends StatelessWidget {
  const LumoPrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.enabled = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: LumoMotion.duration,
      curve: LumoMotion.curve,
      height: LumoSizes.primaryButtonHeight,
      decoration: BoxDecoration(
        gradient: enabled ? LumoGradients.lumoFillGradient : null,
        color: enabled ? null : LumoColors.muted,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
        boxShadow: enabled ? LumoShadows.small : null,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: enabled ? onPressed : null,
          borderRadius: BorderRadius.circular(LumoRadius.pill),
          splashColor: Colors.transparent,
          highlightColor: Colors.transparent,
          child: Center(
            child: Text(
              label,
              style: LumoTypography.buttonPrimary.copyWith(
                color: enabled ? LumoColors.primaryForeground : LumoColors.mutedForeground,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class LumoSecondaryButton extends StatelessWidget {
  const LumoSecondaryButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 40,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(LumoRadius.pill),
        border: Border.all(color: LumoColors.border),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: GestureDetector(
            onTap: onPressed,
            child: Text(label, style: LumoTypography.buttonSecondary),
          ),
        ),
      ),
    );
  }
}

class LumoTextButton extends StatelessWidget {
  const LumoTextButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onPressed,
      child: Text(label, style: LumoTypography.body.copyWith(color: LumoColors.primary)),
    );
  }
}
