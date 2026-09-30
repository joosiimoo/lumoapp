import 'dart:io';

import 'package:flutter/material.dart';
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';
import 'package:lumo/lumo/widgets/lumo_card.dart';
import 'package:lumo/lumo/widgets/lumo_mark.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Stages the server bytes under the server filename.
///
/// `XFile.fromData` ignores [XFile.name] on iOS, Android, and macOS. share_plus
/// then names the staged file from the MIME type, and `text/csv; charset=utf-8`
/// is not a known type, so the sheet receives a `.bin` file.
Future<XFile> salesExportShareFile(
  SalesExportFile file, {
  Directory? directory,
}) async {
  final root = directory ?? await getTemporaryDirectory();
  final filename = _shareFilename(file.filename);
  final target = File('${root.path}${Platform.pathSeparator}$filename');
  await target.writeAsBytes(file.bytes, flush: true);
  return XFile(target.path, mimeType: _shareMimeType(file.mimeType));
}

Future<void> shareSalesExport(SalesExportFile file) async {
  final shared = await salesExportShareFile(file);
  await SharePlus.instance.share(ShareParams(files: [shared]));
}

String _shareMimeType(String mimeType) {
  final mediaType = mimeType.split(';').first.trim();
  if (mediaType.isEmpty) {
    return 'application/octet-stream';
  }
  return mediaType;
}

String _shareFilename(String filename) {
  final parts = filename.trim().split(RegExp(r'[\\/]'));
  final base = parts.isEmpty ? '' : parts.last;
  if (base.isEmpty || base == '.' || base == '..') {
    return 'ventas.csv';
  }
  return base;
}

class HoyPage extends StatefulWidget {
  const HoyPage({
    super.key,
    required this.apiClient,
    this.shareExport,
    this.businessName,
    this.stream,
    this.streamFailed = false,
    this.onPrepareClose,
  });

  final LumoApiClient apiClient;
  final Future<void> Function(SalesExportFile file)? shareExport;
  final String? businessName;
  final BusinessStream? stream;
  final bool streamFailed;
  final VoidCallback? onPrepareClose;

  @override
  State<HoyPage> createState() => _HoyPageState();
}

class _HoyPageState extends State<HoyPage> {
  String? _notice;
  bool _busy = false;

  Future<void> _download(String format) async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _notice = null;
    });
    try {
      final file = await widget.apiClient.downloadCurrentSalesExport(format);
      final share = widget.shareExport ?? shareSalesExport;
      await share(file);
    } on ApiError catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _notice = error.code == 'TENANT_SCOPE_VIOLATION'
            ? 'Todavía no hay actividad de hoy para exportar.'
            : error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _notice = 'No pude descargar el archivo.');
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = widget.businessName?.trim() ?? '';
    final title = name.isEmpty ? 'Así va hoy' : 'Así va $name hoy';
    final stream = widget.stream;
    final summary = stream?.factualSummary;
    return ListView(
      key: const Key('hoy-scroll'),
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 100),
      children: [
        Row(
          children: [
            const LumoMark(size: LumoSizes.markSm),
            const SizedBox(width: 8),
            Text('HOY', style: LumoTypography.eyebrow),
          ],
        ),
        const SizedBox(height: 12),
        Text(title, style: LumoTypography.titleSerifMd),
        const SizedBox(height: 16),
        if (widget.streamFailed)
          LumoCard(
            child: Text(streamUnavailableResponsibility, style: LumoTypography.body),
          )
        else if (stream != null) ...[
          if (summary != null) ...[
            _section(
              'Ventas',
              [
                saleCountLabel(summary.saleCount),
                formatStreamAmount(summary.grossSalesTotal.amount),
              ],
            ),
            const SizedBox(height: 12),
            _section(
              'Pagos',
              [
                'Efectivo ${formatStreamAmount(summary.cashTotal.amount)}',
                'Tarjeta ${formatStreamAmount(summary.cardTotal.amount)}',
                'Transferencia ${formatStreamAmount(summary.transferTotal.amount)}',
              ],
            ),
            const SizedBox(height: 12),
          ],
          _closeCard(stream),
          if (stream.coverageSentence != null) ...[
            const SizedBox(height: 12),
            Text(stream.coverageSentence!, style: LumoTypography.body),
          ],
          const SizedBox(height: 16),
        ],
        LumoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Incluye las ventas confirmadas y anuladas de hoy, con estado explícito en el archivo. Los totales de arriba excluyen ventas anuladas.',
                style: LumoTypography.body,
              ),
              const SizedBox(height: 16),
              LumoSecondaryButton(
                label: 'Descargar Excel',
                onPressed: () => _download('xlsx'),
              ),
              const SizedBox(height: 8),
              LumoSecondaryButton(
                label: 'Descargar CSV',
                onPressed: () => _download('csv'),
              ),
              if (_notice != null) ...[
                const SizedBox(height: 16),
                Text(_notice!, style: LumoTypography.body),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _closeCard(BusinessStream stream) {
    final action = stream.primaryAction;
    final closed = stream.operatorState == 'closed';
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Cierre', style: LumoTypography.eyebrow),
          const SizedBox(height: 8),
          for (final line in _closingLines(stream)) ...[
            Text(line, style: LumoTypography.body),
            const SizedBox(height: 4),
          ],
          if (!closed && action != null) ...[
            const SizedBox(height: 8),
            Text('Confirma efectivo y revisa pendientes', style: LumoTypography.caption),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: LumoPrimaryButton(
                label: action.label,
                onPressed: () => _invoke(action),
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<String> _closingLines(BusinessStream stream) {
    final summary = stream.factualSummary;
    final lines = <String>[_operatorLabel(stream)];
    if (summary != null) {
      lines.add('Esperado ${formatStreamAmount(summary.drawerExpected.amount)}');
      final counted = summary.countedCash;
      if (counted != null) {
        lines.add('Contado ${formatStreamAmount(counted.amount)}');
      }
      final difference = summary.cashDifference;
      if (difference != null) {
        lines.add('Diferencia ${formatStreamAmount(difference.amount)}');
      }
    }
    return lines;
  }

  String _operatorLabel(BusinessStream stream) {
    final summary = stream.factualSummary;
    return switch (stream.operatorState) {
      'closed' => 'Día cerrado',
      'cash_count_required' => 'Falta contar',
      'ready_to_close' || 'cash_difference' => summary == null
          ? stream.responsibility
          : cashStatusLabel(summary.cashStatus),
      'no_active_day' || 'organizing' || 'unavailable' => stream.responsibility,
      _ => stream.responsibility,
    };
  }

  Widget _section(String title, List<String> lines) {
    return LumoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: LumoTypography.eyebrow),
          const SizedBox(height: 8),
          for (final line in lines) ...[
            Text(line, style: LumoTypography.body),
            const SizedBox(height: 4),
          ],
        ],
      ),
    );
  }

  void _invoke(StreamPrimaryAction action) {
    if (action.kind == 'prepare_daily_close' && action.invocation == 'close_workspace') {
      widget.onPrepareClose?.call();
    }
  }
}
