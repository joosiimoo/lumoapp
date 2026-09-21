import 'package:flutter/material.dart';
import 'package:lumo/api/lumo_api_client.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';
import 'package:lumo/core/session/session_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const envName = String.fromEnvironment('LUMO_ENV', defaultValue: 'local');
  final config = await AppConfig.load(envName);
  final session = SessionStore();
  final apiClient = LumoApiClient(config: config, session: session);
  if (config.env == 'local') {
    try {
      final body = await apiClient.get('/api/v1/dev/carrota-token');
      session.accessToken = body['access_token'] as String?;
    } catch (_) {}
  }
  runApp(LumoApp(config: config, apiClient: apiClient));
}
