import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';

class PlaceholderPage extends StatelessWidget {
  const PlaceholderPage({super.key, required this.eyebrow, required this.title, required this.body});

  final String eyebrow;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
      children: [
        Row(
          children: [
            const LumoMark(size: LumoSizes.markSm),
            const SizedBox(width: 8),
            Text(eyebrow.toUpperCase(), style: LumoTypography.eyebrow),
          ],
        ),
        const SizedBox(height: 12),
        Text(title, style: LumoTypography.titleSerifMd),
        const SizedBox(height: 16),
        LumoCard(
          child: Text(body, style: LumoTypography.body),
        ),
      ],
    );
  }
}
