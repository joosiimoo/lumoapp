import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';

class LumoMessage extends StatelessWidget {
  const LumoMessage({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: LumoMark(),
        ),
        const SizedBox(width: 12),
        Expanded(child: Text(text, style: LumoTypography.body)),
      ],
    );
  }
}

class LumoUserMessage extends StatelessWidget {
  const LumoUserMessage({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.85),
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          decoration: const BoxDecoration(
            color: LumoColors.user,
            borderRadius: BorderRadius.all(Radius.circular(LumoRadius.userBubble)),
            boxShadow: LumoShadows.small,
          ),
          child: Text(text, style: LumoTypography.body.copyWith(color: LumoColors.userForeground)),
        ),
      ),
    );
  }
}
