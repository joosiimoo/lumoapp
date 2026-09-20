import 'package:flutter/material.dart';
import 'package:lumo/features/shared/placeholder_page.dart';

class NegocioPage extends StatelessWidget {
  const NegocioPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(
      eyebrow: 'Negocio',
      title: 'Configuración',
      body: 'Catálogo y ajustes vivirán aquí. No hay compositor en esta pantalla.',
    );
  }
}
