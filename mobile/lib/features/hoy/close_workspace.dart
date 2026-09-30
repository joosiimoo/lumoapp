import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lumo/api/api_error.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/typography.dart';
import 'package:lumo/lumo/widgets/lumo_buttons.dart';

/// Server-issued structured cash-count action from a silent prepare response.
GenerativeUiAction? cashCountAction(List<GenerativeUiContract> ui) {
  for (final contract in ui.reversed) {
    if (contract.component != 'daily_close_preparation' || contract.version != 1) {
      continue;
    }
    for (final action in contract.actions) {
      if (action.actionId == 'closing.submit_cash_count@1') {
        return action;
      }
    }
  }
  return null;
}

/// Server-issued confirm action from a silent `request_close` response.
GenerativeUiAction? reviewConfirmationAction(List<GenerativeUiContract> ui) {
  for (final contract in ui.reversed) {
    if (contract.component != 'daily_close_preparation' || contract.version != 1) {
      continue;
    }
    final value = contract.data['confirmation_token'];
    if (value is! String || value.isEmpty) {
      continue;
    }
    for (final action in contract.actions) {
      if (action.actionId == 'closing.confirm@1' && action.contextToken == value) {
        return action;
      }
    }
  }
  return null;
}

Map<String, dynamic>? preparationData(List<GenerativeUiContract> ui) {
  for (final contract in ui.reversed) {
    if (contract.component == 'daily_close_preparation' && contract.version == 1) {
      return contract.data;
    }
  }
  return null;
}

Map<String, dynamic>? confirmedData(List<GenerativeUiContract> ui) {
  for (final contract in ui.reversed) {
    if (contract.component == 'daily_close_confirmed' && contract.version == 1) {
      return contract.data;
    }
  }
  return null;
}

String? moneyFromPayload(Object? value) {
  if (value is! Map) {
    return null;
  }
  final amount = value['amount'];
  if (amount is! String || amount.isEmpty) {
    return null;
  }
  return formatStreamAmount(amount);
}

/// Dedicated Daily Close workspace. Flutter never computes money amounts.
Future<void> showCloseWorkspace({
  required BuildContext context,
  required LumoApiClient apiClient,
  required String conversationId,
  required BusinessStream stream,
  required Future<void> Function() onFinished,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: LumoColors.background,
    builder: (sheetContext) {
      return CloseWorkspaceSheet(
        apiClient: apiClient,
        conversationId: conversationId,
        initialStream: stream,
        onFinished: () async {
          Navigator.of(sheetContext).pop();
          await onFinished();
        },
      );
    },
  );
}

class CloseWorkspaceSheet extends StatefulWidget {
  const CloseWorkspaceSheet({
    super.key,
    required this.apiClient,
    required this.conversationId,
    required this.initialStream,
    required this.onFinished,
  });

  final LumoApiClient apiClient;
  final String conversationId;
  final BusinessStream initialStream;
  final Future<void> Function() onFinished;

  @override
  State<CloseWorkspaceSheet> createState() => _CloseWorkspaceSheetState();
}

class _CloseWorkspaceSheetState extends State<CloseWorkspaceSheet> {
  final _countController = TextEditingController();
  final _noteController = TextEditingController();
  bool _busy = false;
  bool _completed = false;
  bool _noteOpen = false;
  String? _notice;
  GenerativeUiAction? _countAction;
  Map<String, dynamic>? _preparation;
  Map<String, dynamic>? _confirmed;
  late BusinessStream _stream;

  @override
  void initState() {
    super.initState();
    _stream = widget.initialStream;
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    _countController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  bool get _needsCount {
    final status = _cashStatus;
    return status == null || status == 'not_counted';
  }

  String? get _cashStatus {
    final prepared = _preparation?['cash_status'];
    if (prepared is String && prepared.isNotEmpty) {
      return prepared;
    }
    return _stream.factualSummary?.cashStatus;
  }

  String? get _expectedDisplay {
    return moneyFromPayload(_preparation?['expected_cash']) ??
        (_stream.factualSummary == null
            ? null
            : formatStreamAmount(_stream.factualSummary!.drawerExpected.amount));
  }

  String? get _countedDisplay {
    return moneyFromPayload(_preparation?['counted_cash']) ??
        (_stream.factualSummary?.countedCash == null
            ? null
            : formatStreamAmount(_stream.factualSummary!.countedCash!.amount));
  }

  String? get _differenceDisplay {
    return moneyFromPayload(_preparation?['cash_difference']) ??
        (_stream.factualSummary?.cashDifference == null
            ? null
            : formatStreamAmount(_stream.factualSummary!.cashDifference!.amount));
  }

  bool get _hasDifference {
    final status = _cashStatus;
    return status == 'short' || status == 'over';
  }

  Future<void> _bootstrap() async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _notice = null;
    });
    try {
      if (_needsCount) {
        final response = await widget.apiClient.postMessage(
          'preparar el cierre',
          operation: 'lumo.close.prepare.${DateTime.now().microsecondsSinceEpoch}',
          conversationId: widget.conversationId,
        );
        if (!mounted) {
          return;
        }
        setState(() {
          _preparation = preparationData(response.ui);
          _countAction = cashCountAction(response.ui);
          _busy = false;
          if (_countAction == null) {
            _notice = 'No pude preparar el conteo.';
          }
        });
        return;
      }
      setState(() => _busy = false);
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _notice = 'No pude preparar el cierre.';
      });
    }
  }

  Future<void> _submitCount() async {
    final action = _countAction;
    final raw = _countController.text.trim();
    if (action == null || raw.isEmpty || _busy) {
      return;
    }
    setState(() {
      _busy = true;
      _notice = null;
    });
    try {
      final response = await widget.apiClient.postAction(
        actionId: action.actionId,
        optionId: action.optionId,
        contextToken: action.contextToken,
        conversationId: widget.conversationId,
        idempotencyKey: action.idempotencyKey,
        amount: raw,
      );
      if (!mounted) {
        return;
      }
      final prepared = preparationData(response.ui);
      setState(() {
        _preparation = prepared ?? _preparation;
        _countAction = cashCountAction(response.ui);
        _busy = false;
        if (prepared == null || (prepared['cash_status'] == 'not_counted')) {
          _notice = response.text.trim().isEmpty
              ? 'No pude registrar el conteo.'
              : response.text.trim();
        }
      });
    } on ApiError catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _notice = error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _notice = 'No pude registrar el conteo.';
      });
    }
  }

  Future<void> _confirmClose() async {
    if (_busy || _needsCount) {
      return;
    }
    setState(() {
      _busy = true;
      _notice = null;
    });
    try {
      final mint = await widget.apiClient.postMessage(
        'cerrar el día',
        operation: 'lumo.close.request.${DateTime.now().microsecondsSinceEpoch}',
        conversationId: widget.conversationId,
      );
      if (!mounted) {
        return;
      }
      final confirm = reviewConfirmationAction(mint.ui);
      if (confirm == null) {
        setState(() {
          _busy = false;
          _notice = mint.text.trim().isEmpty ? 'No pude preparar el cierre.' : mint.text.trim();
          _preparation = preparationData(mint.ui) ?? _preparation;
        });
        return;
      }
      final note = _noteController.text.trim();
      final response = await widget.apiClient.postAction(
        actionId: confirm.actionId,
        optionId: confirm.optionId,
        contextToken: confirm.contextToken,
        conversationId: widget.conversationId,
        idempotencyKey: confirm.idempotencyKey,
        closeNote: note.isEmpty ? null : note,
      );
      if (!mounted) {
        return;
      }
      final closed = confirmedData(response.ui);
      if (closed == null) {
        setState(() {
          _busy = false;
          _notice = response.text.trim().isEmpty
              ? 'No pude cerrar el día.'
              : response.text.trim();
          _preparation = preparationData(response.ui) ?? _preparation;
        });
        return;
      }
      setState(() {
        _busy = false;
        _completed = true;
        _confirmed = closed;
      });
    } on ApiError catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _notice = error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busy = false;
        _notice = 'No pude cerrar el día.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          key: const Key('close-workspace'),
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          child: _completed ? _completion() : _workspace(),
        ),
      ),
    );
  }

  Widget _workspace() {
    final summary = _stream.factualSummary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Cierre del día', style: LumoTypography.titleSerifMd),
        const SizedBox(height: 8),
        Text(
          'Revisa lo registrado y confirma el efectivo para cerrar.',
          style: LumoTypography.body,
        ),
        if (summary != null) ...[
          const SizedBox(height: 16),
          Text(saleCountLabel(summary.saleCount), style: LumoTypography.body),
          Text(
            'Total ${formatStreamAmount(summary.grossSalesTotal.amount)}',
            style: LumoTypography.body,
          ),
          Text(
            'Efectivo ${formatStreamAmount(summary.cashTotal.amount)}',
            style: LumoTypography.body,
          ),
          Text(
            'Tarjeta ${formatStreamAmount(summary.cardTotal.amount)}',
            style: LumoTypography.body,
          ),
          Text(
            'Transferencia ${formatStreamAmount(summary.transferTotal.amount)}',
            style: LumoTypography.body,
          ),
          if (_expectedDisplay != null)
            Text('Esperado $_expectedDisplay', style: LumoTypography.body),
        ],
        if (_stream.coverageSentence != null) ...[
          const SizedBox(height: 8),
          Text(_stream.coverageSentence!, style: LumoTypography.caption),
        ],
        const SizedBox(height: 20),
        if (_needsCount) ..._countSection() else ..._reconcileSection(),
        const SizedBox(height: 16),
        ..._noteSection(),
        if (!_needsCount) ...[
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: LumoPrimaryButton(
              label: 'Cerrar el día',
              enabled: !_busy,
              onPressed: _confirmClose,
            ),
          ),
        ],
        if (_notice != null) ...[
          const SizedBox(height: 12),
          Text(_notice!, style: LumoTypography.body),
        ],
      ],
    );
  }

  List<Widget> _countSection() {
    final expected = _expectedDisplay ?? r'$0.00';
    return [
      Text(
        'Según las ventas, deberías tener $expected en efectivo.',
        style: LumoTypography.body,
      ),
      const SizedBox(height: 8),
      Text('¿Cuánto contaste?', style: LumoTypography.cardTitle),
      const SizedBox(height: 8),
      TextField(
        key: const Key('close-count-input'),
        controller: _countController,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [
          FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
        ],
        decoration: const InputDecoration(
          hintText: '0.00',
          border: OutlineInputBorder(),
        ),
      ),
      const SizedBox(height: 12),
      SizedBox(
        width: double.infinity,
        child: LumoPrimaryButton(
          label: 'Registrar conteo',
          enabled: !_busy,
          onPressed: _submitCount,
        ),
      ),
    ];
  }

  List<Widget> _reconcileSection() {
    final status = _cashStatus;
    final statusLabel = status == null ? null : cashStatusLabel(status);
    return [
      if (_expectedDisplay != null) Text('Esperado $_expectedDisplay', style: LumoTypography.body),
      if (_countedDisplay != null) Text('Contado $_countedDisplay', style: LumoTypography.body),
      if (_differenceDisplay != null) Text('Diferencia $_differenceDisplay', style: LumoTypography.body),
      if (statusLabel != null) ...[
        const SizedBox(height: 8),
        Text(statusLabel, style: LumoTypography.cardTitle),
      ],
      if (_hasDifference) ...[
        const SizedBox(height: 8),
        Text(
          'Puedes agregar una nota opcional para explicar el faltante o sobrante.',
          style: LumoTypography.body,
        ),
      ],
    ];
  }

  List<Widget> _noteSection() {
    final emphasize = _hasDifference;
    return [
      if (!_noteOpen)
        LumoSecondaryButton(
          label: 'Agregar nota',
          onPressed: _busy
              ? () {}
              : () => setState(() => _noteOpen = true),
        )
      else ...[
        Text(
          emphasize ? 'Nota (opcional, explica la diferencia)' : 'Nota (opcional)',
          style: emphasize ? LumoTypography.cardTitle : LumoTypography.body,
        ),
        const SizedBox(height: 8),
        TextField(
          key: const Key('close-note-input'),
          controller: _noteController,
          maxLength: 500,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'Agregar nota',
            border: OutlineInputBorder(),
          ),
        ),
      ],
    ];
  }

  Widget _completion() {
    final data = _confirmed ?? const <String, dynamic>{};
    final status = data['cash_status'];
    final statusLabel = status is String ? cashStatusLabel(status) : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Día cerrado', style: LumoTypography.titleSerifMd),
        const SizedBox(height: 12),
        if (moneyFromPayload(data['expected_cash']) != null)
          Text('Esperado ${moneyFromPayload(data['expected_cash'])}', style: LumoTypography.body),
        if (moneyFromPayload(data['counted_cash']) != null)
          Text('Contado ${moneyFromPayload(data['counted_cash'])}', style: LumoTypography.body),
        if (moneyFromPayload(data['cash_difference']) != null)
          Text(
            'Diferencia ${moneyFromPayload(data['cash_difference'])}',
            style: LumoTypography.body,
          ),
        if (statusLabel != null) ...[
          const SizedBox(height: 8),
          Text(statusLabel, style: LumoTypography.cardTitle),
        ],
        if (data['close_note'] is String && (data['close_note'] as String).isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(data['close_note'] as String, style: LumoTypography.body),
        ],
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          child: LumoPrimaryButton(
            label: 'Listo',
            onPressed: () => widget.onFinished(),
          ),
        ),
      ],
    );
  }
}
