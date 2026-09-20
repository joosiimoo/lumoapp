import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_bottom_navigation.dart';

class LumoScaffold extends StatelessWidget {
  const LumoScaffold({
    super.key,
    required this.body,
    this.footer,
    this.showTabBar = true,
    this.currentTab = LumoTab.inicio,
    this.onSelectTab,
  });

  final Widget body;
  final Widget? footer;
  final bool showTabBar;
  final LumoTab currentTab;
  final ValueChanged<LumoTab>? onSelectTab;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: LumoColors.background,
      body: SafeArea(
        bottom: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
            child: Column(
              children: [
                Expanded(child: body),
                if (footer != null)
                  ClipRect(
                    child: BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                      child: ColoredBox(
                        color: LumoColors.background.withValues(alpha: 0.95),
                        child: footer,
                      ),
                    ),
                  ),
                if (showTabBar)
                  ClipRect(
                    child: BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                      child: LumoBottomNavigation(
                        current: currentTab,
                        onSelect: onSelectTab ?? (_) {},
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LumoToast {
  static void show(BuildContext context, String message) {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;
    entry = OverlayEntry(
      builder: (context) {
        return Positioned(
          top: MediaQuery.paddingOf(context).top + 12,
          left: 16,
          right: 16,
          child: Align(
            alignment: Alignment.topCenter,
            child: Material(
              color: Colors.transparent,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: LumoSizes.contentMaxWidth),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: LumoColors.surfaceElevated,
                    borderRadius: BorderRadius.circular(LumoRadius.lg),
                    boxShadow: LumoShadows.small,
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    child: Text(message, style: LumoTypography.body, textAlign: TextAlign.center),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
    overlay.insert(entry);
    Future<void>.delayed(const Duration(seconds: 2), () {
      if (entry.mounted) {
        entry.remove();
      }
    });
  }
}
