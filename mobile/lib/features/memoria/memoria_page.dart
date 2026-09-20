import 'package:flutter/material.dart';
import 'package:lumo/features/shared/placeholder_page.dart';

class MemoriaPage extends StatelessWidget {
  const MemoriaPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(
      eyebrow: 'Memoria',
      title: 'Lo que Lumo recuerda',
      body: 'La memoria factual se habilitará cuando existan eventos confirmados.',
    );
  }
}
