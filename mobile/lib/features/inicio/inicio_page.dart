import 'package:flutter/material.dart';
import 'package:lumo/features/shared/placeholder_page.dart';

class InicioPage extends StatelessWidget {
  const InicioPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(
      eyebrow: 'Lumo · negocio',
      title: 'Buenos días',
      body: 'El stream del negocio estará aquí. La captura conversacional llega en un cambio posterior.',
    );
  }
}
