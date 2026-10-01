import 'package:flutter/material.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/features/memoria/memoria_timeline.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';
import 'package:lumo/lumo/widgets/lumo_scaffold.dart';

class MemoriaPage extends StatefulWidget {
  const MemoriaPage({super.key, required this.apiClient, this.onAfterVoid});

  final LumoApiClient apiClient;
  final Future<void> Function()? onAfterVoid;

  @override
  State<MemoriaPage> createState() => _MemoriaPageState();
}

class _MemoriaPageState extends State<MemoriaPage> {
  final List<Map<String, dynamic>> _events = [];
  String? _nextCursor;
  String _businessToday = '';
  String _businessYesterday = '';
  var _loading = true;
  var _loadingMore = false;
  String? _error;
  String? _busyKey;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({String? before}) async {
    try {
      final body = await widget.apiClient.getMemoryEvents(before: before);
      if (!mounted) {
        return;
      }
      final raw = body['events'];
      final page = raw is List
          ? raw.whereType<Map>().map((event) => Map<String, dynamic>.from(event)).toList()
          : <Map<String, dynamic>>[];
      setState(() {
        if (before == null) {
          _events
            ..clear()
            ..addAll(page);
        } else {
          _events.addAll(page);
        }
        _nextCursor = body['next_cursor'] as String?;
        _businessToday = body['business_today'] as String? ?? '';
        _businessYesterday = body['business_yesterday'] as String? ?? '';
        _loading = false;
        _loadingMore = false;
        _error = null;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _loadingMore = false;
        _error = 'No pude cargar Memoria.';
      });
    }
  }

  Future<void> _startVoid(MemoriaFeedItem item) async {
    final action = item.voidRequest;
    final conversationId = item.voidConversationId;
    if (action == null || conversationId == null || _busyKey != null) {
      return;
    }
    setState(() => _busyKey = action.idempotencyKey);
    try {
      final response = await widget.apiClient.postAction(
        actionId: action.actionId,
        optionId: action.optionId,
        contextToken: action.contextToken,
        conversationId: conversationId,
        idempotencyKey: action.idempotencyKey,
      );
      if (!mounted) {
        return;
      }
      GenerativeUiContract? confirmUi;
      for (final contract in response.ui) {
        if (contract.component == 'sale_confirmed' &&
            contract.actions.any((item) => item.actionId == voidConfirmActionId)) {
          confirmUi = contract;
          break;
        }
      }
      if (confirmUi == null) {
        setState(() => _busyKey = null);
        LumoToast.show(context, response.text.trim().isEmpty ? 'No pude anular esa venta.' : response.text);
        return;
      }
      final sheetContract = confirmUi;
      setState(() => _busyKey = null);
      final confirmed = await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        backgroundColor: LumoColors.background,
        builder: (sheetContext) {
          return Padding(
            padding: EdgeInsets.only(
              left: 20,
              right: 20,
              top: 20,
              bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 24,
            ),
            child: SingleChildScrollView(
              child: SaleConfirmedView(
                contract: sheetContract,
                chrome: UiActionChrome(
                  onAction: (confirmAction, {voidReason}) async {
                    Navigator.of(sheetContext).pop(true);
                    await _confirmVoid(
                      action: confirmAction,
                      conversationId: conversationId,
                      voidReason: voidReason,
                    );
                  },
                ),
              ),
            ),
          );
        },
      );
      if (confirmed != true && mounted) {
        setState(() => _busyKey = null);
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _busyKey = null);
      LumoToast.show(context, 'No pude anular esa venta.');
    }
  }

  Future<void> _confirmVoid({
    required GenerativeUiAction action,
    required String conversationId,
    String? voidReason,
  }) async {
    setState(() => _busyKey = action.idempotencyKey);
    try {
      final response = await widget.apiClient.postAction(
        actionId: action.actionId,
        optionId: action.optionId,
        contextToken: action.contextToken,
        conversationId: conversationId,
        idempotencyKey: action.idempotencyKey,
        voidReason: voidReason,
      );
      if (!mounted) {
        return;
      }
      setState(() => _busyKey = null);
      await _load();
      await widget.onAfterVoid?.call();
      if (!mounted) {
        return;
      }
      if (response.text.trim().isNotEmpty) {
        LumoToast.show(context, response.text);
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _busyKey = null);
      LumoToast.show(context, 'No pude anular esa venta.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final groups = memoriaGroups(
      events: _events,
      businessToday: _businessToday,
      businessYesterday: _businessYesterday,
    );
    return ColoredBox(
      color: LumoColors.background,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
        children: [
          Text('MEMORIA', style: LumoTypography.eyebrow),
          const SizedBox(height: 8),
          Text('Lo que Lumo recuerda', style: LumoTypography.titleSerifMd),
          const SizedBox(height: 24),
          if (_loading)
            const Center(child: CircularProgressIndicator())
          else if (_error != null)
            Text(_error!, style: LumoTypography.inter(size: 15))
          else if (groups.isEmpty)
            Text(
              memoriaEmptyTitle,
              style: LumoTypography.inter(size: 15, color: LumoColors.mutedForeground),
            )
          else
            for (final group in groups) ...[
              Text(group.label, style: LumoTypography.sectionLabel),
              const SizedBox(height: 10),
              _MemoriaActivitySurface(
                items: group.items,
                busyKey: _busyKey,
                onVoid: _startVoid,
              ),
              const SizedBox(height: 24),
            ],
          if (!_loading && _nextCursor != null)
            LumoTextButton(
              label: 'Ver anteriores',
              onPressed: () {
                if (_loadingMore || _nextCursor == null) {
                  return;
                }
                setState(() => _loadingMore = true);
                _load(before: _nextCursor);
              },
            ),
        ],
      ),
    );
  }
}

/// One shared white Activity surface per date group — timeline rows, not cards.
class _MemoriaActivitySurface extends StatelessWidget {
  const _MemoriaActivitySurface({
    required this.items,
    required this.busyKey,
    required this.onVoid,
  });

  final List<MemoriaFeedItem> items;
  final String? busyKey;
  final Future<void> Function(MemoriaFeedItem item) onVoid;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: LumoColors.surfaceElevated,
        borderRadius: BorderRadius.circular(LumoRadius.card),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
            child: Text('ACTIVIDAD', style: LumoTypography.sectionLabel),
          ),
          for (var index = 0; index < items.length; index++)
            MemoriaTimelineEvent(
              item: items[index],
              connectAbove: index > 0,
              connectBelow: index < items.length - 1,
              busyKey: busyKey,
              onVoid: onVoid,
            ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

/// Testable timeline event row: green node + optional connector + content.
class MemoriaTimelineEvent extends StatelessWidget {
  const MemoriaTimelineEvent({
    super.key,
    required this.item,
    required this.connectAbove,
    required this.connectBelow,
    required this.busyKey,
    required this.onVoid,
  });

  final MemoriaFeedItem item;
  final bool connectAbove;
  final bool connectBelow;
  final String? busyKey;
  final Future<void> Function(MemoriaFeedItem item) onVoid;

  static const double _railWidth = 18;
  static const double _nodeCenterY = 22;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              width: _railWidth,
              child: CustomPaint(
                painter: MemoriaTimelineRailPainter(
                  connectAbove: connectAbove,
                  connectBelow: connectBelow,
                  nodeCenterY: _nodeCenterY,
                ),
                child: const SizedBox.expand(),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(top: 12, bottom: 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Text(
                          item.localTime,
                          style: LumoTypography.inter(size: 12, color: LumoColors.mutedForeground),
                        ),
                        const SizedBox(width: 8),
                        _TypeChip(label: item.typeLabel),
                        const Spacer(),
                        if (item.voidRequest != null)
                          TextButton(
                            onPressed: busyKey == null ? () => onVoid(item) : null,
                            style: TextButton.styleFrom(
                              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                            child: Text(
                              'Anular',
                              style: LumoTypography.buttonSecondary.copyWith(
                                fontSize: 13,
                                color: busyKey == null ? LumoColors.primary : LumoColors.mutedForeground,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item.primary,
                      style: LumoTypography.inter(size: 14, weight: FontWeight.w500),
                    ),
                    if (item.reference != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        item.reference!,
                        style: LumoTypography.inter(size: 12, color: LumoColors.mutedForeground),
                      ),
                    ],
                    if (item.secondary != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        item.secondary!,
                        style: LumoTypography.inter(size: 13, color: LumoColors.mutedForeground),
                      ),
                    ],
                    if (item.note != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        item.note!,
                        style: LumoTypography.inter(size: 13, color: LumoColors.mutedForeground),
                      ),
                    ],
                    if (item.statusChip != null) ...[
                      const SizedBox(height: 6),
                      LumoStatusChip(label: item.statusChip!),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Paints the green node and vertical connector segments for one event.
class MemoriaTimelineRailPainter extends CustomPainter {
  const MemoriaTimelineRailPainter({
    required this.connectAbove,
    required this.connectBelow,
    required this.nodeCenterY,
  });

  final bool connectAbove;
  final bool connectBelow;
  final double nodeCenterY;

  static const _nodeRadius = 4.0;

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final linePaint = Paint()
      ..color = LumoColors.primary.withValues(alpha: 0.28)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final nodePaint = Paint()
      ..color = LumoColors.primary
      ..style = PaintingStyle.fill;

    if (connectAbove) {
      canvas.drawLine(Offset(cx, 0), Offset(cx, nodeCenterY - _nodeRadius), linePaint);
    }
    canvas.drawCircle(Offset(cx, nodeCenterY), _nodeRadius, nodePaint);
    if (connectBelow) {
      canvas.drawLine(Offset(cx, nodeCenterY + _nodeRadius), Offset(cx, size.height), linePaint);
    }
  }

  @override
  bool shouldRepaint(covariant MemoriaTimelineRailPainter oldDelegate) {
    return connectAbove != oldDelegate.connectAbove ||
        connectBelow != oldDelegate.connectBelow ||
        nodeCenterY != oldDelegate.nodeCenterY;
  }
}

class _TypeChip extends StatelessWidget {
  const _TypeChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: LumoColors.secondary,
        borderRadius: BorderRadius.circular(LumoRadius.pill),
      ),
      child: Text(
        label,
        style: LumoTypography.inter(size: 11, weight: FontWeight.w500, color: LumoColors.foreground),
      ),
    );
  }
}
