import 'package:flutter/material.dart';
import 'package:lumo/app/lumo_app.dart';
import 'package:lumo/core/env/app_config.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const envName = String.fromEnvironment('LUMO_ENV', defaultValue: 'local');
  final config = await AppConfig.load(envName);
  runApp(LumoApp(config: config));
}
