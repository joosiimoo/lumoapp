import 'dart:convert';

import 'package:flutter/services.dart';

class AppConfig {
  const AppConfig({required this.env, required this.apiBaseUrl});

  final String env;
  final String apiBaseUrl;

  static Future<AppConfig> load(String envName) async {
    final raw = await rootBundle.loadString('assets/config/$envName.json');
    final json = jsonDecode(raw) as Map<String, dynamic>;
    return AppConfig(
      env: json['env'] as String,
      apiBaseUrl: json['apiBaseUrl'] as String,
    );
  }
}
