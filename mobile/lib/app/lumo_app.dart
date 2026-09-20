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
import 'package:lumo/lumo/tokens.dart';
import 'package:lumo/lumo/widgets/lumo_composer.dart';
import 'package:lumo/lumo/widgets/lumo_scaffold.dart';
import 'package:lumo/lumo/widgets/lumo_bottom_navigation.dart';

class LumoApp extends StatelessWidget {
  const LumoApp({super.key, required this.config, this.apiClient});

  final AppConfig config;
  final LumoApiClient? apiClient;

  @override
  Widget build(BuildContext context) {
    final session = SessionStore();
    final client = apiClient ?? LumoApiClient(config: config, session: session);
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
      home: LumoHome(config: config, apiClient: client),
    );
  }
}

class LumoHome extends StatefulWidget {
  const LumoHome({super.key, required this.config, required this.apiClient});

  final AppConfig config;
  final LumoApiClient apiClient;

  @override
  State<LumoHome> createState() => _LumoHomeState();
}

class _LumoHomeState extends State<LumoHome> {
  LumoTab _tab = LumoTab.inicio;
  final _composer = TextEditingController();

  @override
  void dispose() {
    _composer.dispose();
    super.dispose();
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
              onSend: () {
                _composer.clear();
                LumoToast.show(context, 'Conversación — próximamente');
              },
            )
          : null,
      body: switch (_tab) {
        LumoTab.inicio => const InicioPage(),
        LumoTab.hoy => const HoyPage(),
        LumoTab.memoria => const MemoriaPage(),
        LumoTab.negocio => const NegocioPage(),
      },
    );
  }
}
