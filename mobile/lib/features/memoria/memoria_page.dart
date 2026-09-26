import 'package:flutter/material.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/features/memoria/memoria_timeline.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_chips.dart';

class MemoriaPage extends StatefulWidget {
  const MemoriaPage({super.key, required this.apiClient});

  final LumoApiClient apiClient;

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
          else if (groups.isEmpty) ...[
            Text(memoriaEmptyTitle, style: LumoTypography.inter(size: 18, weight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(memoriaEmptyBody, style: LumoTypography.inter(size: 15, color: LumoColors.mutedForeground)),
          ] else
            for (final group in groups) ...[
              Text(group.label, style: LumoTypography.sectionLabel),
              const SizedBox(height: 10),
              for (final card in group.cards) ...[
                LumoCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(card.title, style: LumoTypography.inter(size: 16, weight: FontWeight.w600)),
                      for (final line in card.lines)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(line, style: LumoTypography.inter(size: 15)),
                        ),
                      if (card.chip != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: LumoStatusChip(label: card.chip!),
                        ),
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          card.localTime,
                          style: LumoTypography.inter(size: 13, color: LumoColors.mutedForeground),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
              ],
              const SizedBox(height: 12),
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
          if (!_loading && _error == null) ...[
            const SizedBox(height: 16),
            Text(
              memoriaFooter,
              style: LumoTypography.inter(size: 13, color: LumoColors.mutedForeground),
            ),
          ],
        ],
      ),
    );
  }
}
