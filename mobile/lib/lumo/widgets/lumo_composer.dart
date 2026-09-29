import 'package:flutter/material.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';

class LumoComposer extends StatefulWidget {
  const LumoComposer({
    super.key,
    required this.controller,
    required this.onSend,
    this.focusNode,
    this.emphasized = false,
  });

  static const shellKey = ValueKey('lumo_composer');

  final TextEditingController controller;
  final VoidCallback onSend;
  final FocusNode? focusNode;
  final bool emphasized;

  @override
  State<LumoComposer> createState() => _LumoComposerState();
}

class _LumoComposerState extends State<LumoComposer> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
  }

  @override
  void didUpdateWidget(covariant LumoComposer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_onChanged);
      widget.controller.addListener(_onChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    super.dispose();
  }

  void _onChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final hasText = widget.controller.text.trim().isNotEmpty;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: KeyedSubtree(
        key: LumoComposer.shellKey,
        child: _buildShell(hasText),
      ),
    );
  }

  Widget _buildShell(bool hasText) {
    return AnimatedContainer(
      duration: LumoMotion.duration,
      curve: LumoMotion.curve,
      height: LumoSizes.composerHeight + 8,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: LumoColors.surfaceElevated,
        borderRadius: const BorderRadius.all(Radius.circular(LumoRadius.pill)),
        border: widget.emphasized ? Border.all(color: LumoColors.ring, width: 2) : null,
        boxShadow: widget.emphasized ? LumoShadows.ringLumo : LumoShadows.small,
      ),
      child: Row(
          children: [
            SizedBox(
              width: LumoSizes.composerIconButton,
              height: LumoSizes.composerIconButton,
              child: const Icon(Icons.photo_camera_outlined, size: 18, color: LumoColors.mutedForeground),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: widget.controller,
                focusNode: widget.focusNode,
                style: LumoTypography.input,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) {
                  if (widget.controller.text.trim().isNotEmpty) {
                    widget.onSend();
                  }
                },
                decoration: InputDecoration(
                  isDense: true,
                  border: InputBorder.none,
                  hintText: 'Dile algo a tu negocio…',
                  hintStyle: LumoTypography.input.copyWith(color: LumoColors.mutedForeground),
                ),
              ),
            ),
            const SizedBox(width: 8),
            if (hasText)
              GestureDetector(
                onTap: widget.onSend,
                child: Container(
                  width: LumoSizes.sendButton,
                  height: LumoSizes.sendButton,
                  decoration: const BoxDecoration(
                    gradient: LumoGradients.lumoFillGradient,
                    shape: BoxShape.circle,
                    boxShadow: LumoShadows.small,
                  ),
                  child: const Icon(Icons.arrow_upward, size: 16, color: Colors.white),
                ),
              )
            else
              const SizedBox(
                width: LumoSizes.composerIconButton,
                height: LumoSizes.composerIconButton,
                child: Icon(Icons.mic_none, size: 18, color: LumoColors.mutedForeground),
              ),
          ],
        ),
    );
  }
}
