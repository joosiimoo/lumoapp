import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';
import 'package:lumo/features/hoy/close_workspace.dart';
import 'package:lumo/features/hoy/hoy_page.dart';
import 'package:lumo/features/inicio/business_stream.dart';
import 'package:lumo/features/inicio/inicio_page.dart';
import 'package:lumo/features/memoria/memoria_page.dart';
import 'package:lumo/features/negocio/negocio_page.dart';
import 'package:lumo/features/onboarding/onboarding_page.dart';
import 'package:lumo/features/onboarding/startup.dart';
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
  final _composerFocus = FocusNode();
  final List<InicioTurn> _inicio = [];
  bool _sending = false;
  String? _pendingOperation;
  String? _businessName;
  String? _confirmationToken;
  late final String _conversationId;
  final Set<String> _settledCards = {};
  String? _busyCardKey;
  String? _busyActionKey;
  BusinessStream? _stream;
  bool _streamFailed = false;
  bool _onboarding = false;
  String _onboardingPrompt = '¿Cómo se llama tu negocio?';
  String? _nextField;
  List<GenerativeUiContract> _onboardingCards = const [];

  @override
  void initState() {
    super.initState();
    _conversationId = const Uuid().v4();
    _loadBusiness();
  }

  Future<void> _loadBusiness() async {
    if (widget.apiClient.session.accessToken == null) {
      await _loadStream();
      return;
    }
    try {
      final body = await widget.apiClient.getSession();
      if (!mounted) {
        return;
      }
      if (destinationForSession(body) == StartupDestination.onboarding) {
        _showOnboarding(body);
        return;
      }
      final business = body['business'];
      if (business is Map && mounted) {
        setState(() {
          _onboarding = false;
          _businessName = '${business['name'] ?? ''}';
        });
      }
    } catch (_) {}
    if (mounted && !_onboarding) {
      await _loadStream();
    }
  }

  void _showOnboarding(Map<String, dynamic> body) {
    final next = body['next_required_field'] as String?;
    final card = confirmationCardFromState(body);
    setState(() {
      _onboarding = true;
      _stream = null;
      _nextField = next;
      _onboardingCards = card == null ? const [] : [card];
      _onboardingPrompt = next == 'ready_to_complete'
          ? 'Revisa tu negocio antes de empezar.'
          : '¿Cómo se llama tu negocio?';
    });
  }

  Future<void> _onOnboardingSend(String text) async {
    final body = onboardingApplyBody(text, _nextField);
    if (body == null) {
      return;
    }
    try {
      final response = await widget.apiClient.applyOnboarding(
        body,
        idempotencyKey: 'onboarding-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (!mounted) {
        return;
      }
      if (response['onboarding_status'] == 'completed') {
        setState(() => _onboarding = false);
        await _loadStream();
        return;
      }
      _showOnboarding(response);
    } catch (_) {
      if (mounted) {
        LumoToast.show(context, 'No pude registrar eso. Intenta de nuevo.');
      }
    }
  }

  Future<void> _onStartUsingLumo() async {
    try {
      final response = await widget.apiClient.applyOnboarding(
        {'start_using_lumo': true},
        idempotencyKey: 'start_using_lumo',
      );
      if (!mounted) {
        return;
      }
      if (response['onboarding_status'] == 'completed') {
        final businessName = response['name'];
        setState(() {
          _onboarding = false;
          _onboardingCards = const [];
          _nextField = null;
          if (businessName is String) {
            _businessName = businessName;
          }
        });
        await _loadStream();
      }
    } catch (_) {
      if (mounted) {
        LumoToast.show(context, 'No pude registrar eso. Intenta de nuevo.');
      }
    }
  }

  Future<void> _loadStream() async {
    try {
      final body = await widget.apiClient.getBusinessStreamToday();
      if (!mounted) {
        return;
      }
      final next = BusinessStream.fromJson(body);
      setState(() {
        _stream = next;
        _streamFailed = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _stream = null;
        _streamFailed = true;
      });
    }
  }

  bool _showsOperationalState(LumoTab tab) {
    return tab == LumoTab.inicio || tab == LumoTab.hoy;
  }

  Future<void> _openCloseWorkspace() async {
    final current = _stream;
    final action = current?.primaryAction;
    if (current == null ||
        action == null ||
        action.kind != 'prepare_daily_close' ||
        action.invocation != 'close_workspace') {
      return;
    }
    await showCloseWorkspace(
      context: context,
      apiClient: widget.apiClient,
      conversationId: _conversationId,
      stream: current,
      onFinished: _loadStream,
    );
  }

  @override
  void dispose() {
    _composerFocus.dispose();
    _composer.dispose();
    super.dispose();
  }

  Future<void> _onAction(GenerativeUiContract contract, GenerativeUiAction action, {String? voidReason}) async {
    final cardKey = uiCardKey(contract);
    if (_busyCardKey != null ||
        _settledCards.contains(cardKey) ||
        _tab != LumoTab.inicio ||
        _stream?.operatorState == 'closed') {
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
        voidReason: voidReason,
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
      await _loadStream();
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
      await _loadStream();
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
    if (_onboarding) {
      return OnboardingPage(
        prompt: _onboardingPrompt,
        cards: _onboardingCards,
        onSend: _onOnboardingSend,
        onStartUsingLumo: _onStartUsingLumo,
      );
    }
    final showComposer = _tab != LumoTab.negocio && _tab != LumoTab.memoria;
    return LumoScaffold(
      currentTab: _tab,
      onSelectTab: (tab) {
        setState(() => _tab = tab);
        if (_showsOperationalState(tab)) {
          _loadStream();
        }
      },
      footer: showComposer
          ? LumoComposer(
              controller: _composer,
              focusNode: _composerFocus,
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
            stream: _stream,
            streamFailed: _streamFailed,
            onRetryStream: _loadStream,
          ),
        LumoTab.hoy => HoyPage(
            apiClient: widget.apiClient,
            businessName: _businessName,
            stream: _stream,
            streamFailed: _streamFailed,
            onPrepareClose: _openCloseWorkspace,
          ),
        LumoTab.memoria => MemoriaPage(apiClient: widget.apiClient),
        LumoTab.negocio => const NegocioPage(),
      },
    );
  }
}
