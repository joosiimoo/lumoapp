import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/hoy/hoy_page.dart';
import 'package:lumo/features/inicio/inicio_page.dart';
import 'package:lumo/features/memoria/memoria_page.dart';
import 'package:lumo/features/negocio/negocio_page.dart';
import 'package:lumo/features/onboarding/onboarding_page.dart';
import 'package:lumo/lumo/generative_ui/renderer.dart';
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/widgets/lumo_composer.dart';
import 'package:lumo/lumo/widgets/lumo_scaffold.dart';
import 'package:lumo/lumo/widgets/lumo_bottom_navigation.dart';
import 'package:uuid/uuid.dart';

/// Keeps the latest non-null preparation token. A null token or a confirmed card clears it.
/// A confirm action token is sent only when it matches `data.confirmation_token`.
String? nextConfirmationToken(List<GenerativeUiContract> ui, String? current) {
  var token = current;
  for (final contract in ui) {
    if (contract.component == 'daily_close_confirmed') {
      token = null;
    } else if (contract.component == 'daily_close_preparation') {
      final value = contract.data['confirmation_token'];
      final dataToken = value is String && value.isNotEmpty ? value : null;
      GenerativeUiAction? confirm;
      for (final action in contract.actions) {
        if (action.actionId == 'closing.confirm@1') {
          confirm = action;
        }
      }
      if (confirm == null) {
        token = dataToken;
      } else if (dataToken != confirm.contextToken) {
        token = null;
      } else {
        token = confirm.contextToken;
      }
    }
  }
  return token;
}

class LumoApp extends StatelessWidget {
  const LumoApp({super.key, required this.config, this.apiClient});

  final AppConfig config;
  final LumoApiClient? apiClient;

  @override
  Widget build(BuildContext context) {
    final client = apiClient ?? LumoApiClient(config: config, session: SessionStore());
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      locale: const Locale('es'),
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        scaffoldBackgroundColor: LumoColors.background,
        colorScheme: const ColorScheme.light(
          primary: LumoColors.primary,
          surface: LumoColors.background,
        ),
        textTheme: GoogleFonts.interTextTheme(),
      ),
      routes: {
        '/onboarding': (_) => const OnboardingPage(),
      },
      home: LumoHome(apiClient: client),
    );
  }
}

class LumoHome extends StatefulWidget {
  const LumoHome({super.key, required this.apiClient});

  final LumoApiClient apiClient;

  @override
  State<LumoHome> createState() => _LumoHomeState();
}

class _LumoHomeState extends State<LumoHome> {
  LumoTab _tab = LumoTab.inicio;
  final _composer = TextEditingController();
  final List<InicioTurn> _inicio = [];
  bool _sending = false;
  String? _pendingOperation;
  String? _businessName;
  String? _confirmationToken;
  late final String _conversationId;
  final Set<String> _settledCards = {};
  String? _busyCardKey;
  String? _busyActionKey;

  @override
  void initState() {
    super.initState();
    _conversationId = const Uuid().v4();
    _loadBusiness();
  }

  Future<void> _loadBusiness() async {
    if (widget.apiClient.session.accessToken == null) {
      return;
    }
    try {
      final body = await widget.apiClient.getSession();
      final business = body['business'];
      if (!mounted || business is! Map) {
        return;
      }
      setState(() => _businessName = '${business['name'] ?? ''}');
    } catch (_) {}
  }

  @override
  void dispose() {
    _composer.dispose();
    super.dispose();
  }

  Future<void> _onAction(GenerativeUiContract contract, GenerativeUiAction action) async {
    final cardKey = uiCardKey(contract);
    if (_busyCardKey != null || _settledCards.contains(cardKey) || _tab != LumoTab.inicio) {
      return;
    }
    setState(() {
      _busyCardKey = cardKey;
      _busyActionKey = action.idempotencyKey;
    });
    try {
      final response = await widget.apiClient.postAction(
        actionId: action.actionId,
        optionId: action.optionId,
        contextToken: action.contextToken,
        conversationId: _conversationId,
        idempotencyKey: action.idempotencyKey,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _inicio.add(InicioTurn.assistant(response.text, response.ui));
        _confirmationToken = nextConfirmationToken(response.ui, _confirmationToken);
        _settledCards.add(cardKey);
        _busyCardKey = null;
        _busyActionKey = null;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _busyCardKey = null;
        _busyActionKey = null;
      });
      LumoToast.show(context, 'No pude registrar eso. Intenta de nuevo.');
    }
  }

  Future<void> _onSend() async {
    if (_tab != LumoTab.inicio) {
      LumoToast.show(context, 'Conversación — próximamente');
      return;
    }
    final text = _composer.text.trim();
    if (text.isEmpty || _sending) {
      return;
    }
    _composer.clear();
    final operation = _pendingOperation ?? 'lumo.message.send.${DateTime.now().microsecondsSinceEpoch}';
    _pendingOperation = operation;
    setState(() {
      final last = _inicio.isEmpty ? null : _inicio.last;
      if (last == null || !last.fromUser || last.text != text) {
        _inicio.add(InicioTurn.user(text));
      }
      _sending = true;
    });
    try {
      final response = await widget.apiClient.postMessage(
        text,
        operation: operation,
        conversationId: _conversationId,
        confirmationToken: _confirmationToken,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _inicio.add(InicioTurn.assistant(response.text, response.ui));
        _confirmationToken = nextConfirmationToken(response.ui, _confirmationToken);
        _sending = false;
        _pendingOperation = null;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _sending = false);
      _composer
        ..text = text
        ..selection = TextSelection.collapsed(offset: text.length);
      LumoToast.show(context, 'No pude registrar eso. Intenta de nuevo.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final showComposer = _tab != LumoTab.negocio;
    return LumoScaffold(
      currentTab: _tab,
      onSelectTab: (tab) => setState(() => _tab = tab),
      footer: showComposer
          ? LumoComposer(
              controller: _composer,
              onSend: _onSend,
            )
          : null,
      body: switch (_tab) {
        LumoTab.inicio => InicioPage(
            messages: _inicio,
            businessName: _businessName,
            onAction: _onAction,
            disabledCardKeys: _settledCards,
            busyCardKey: _busyCardKey,
            busyActionKey: _busyActionKey,
          ),
        LumoTab.hoy => HoyPage(
            apiClient: widget.apiClient,
            conversationId: _conversationId,
            onSwitchToInicio: () => setState(() => _tab = LumoTab.inicio),
          ),
        LumoTab.memoria => const MemoriaPage(),
        LumoTab.negocio => const NegocioPage(),
      },
    );
  }
}
