import 'dart:io';

import 'package:flutter/material.dart';
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/lumo_api_client.dart';
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
  const HoyPage({super.key, required this.apiClient, this.shareExport});

  final LumoApiClient apiClient;
  final Future<void> Function(SalesExportFile file)? shareExport;

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
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
      children: [
        Row(
          children: [
            const LumoMark(size: LumoSizes.markSm),
            const SizedBox(width: 8),
            Text('HOY', style: LumoTypography.eyebrow),
          ],
        ),
        const SizedBox(height: 12),
        Text('Jornada', style: LumoTypography.titleSerifMd),
        const SizedBox(height: 16),
        LumoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Incluye las ventas confirmadas de hoy.', style: LumoTypography.body),
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
}
