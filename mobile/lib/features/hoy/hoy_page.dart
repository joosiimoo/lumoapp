import 'package:flutter/material.dart';
import 'package:lumo/features/shared/placeholder_page.dart';

class HoyPage extends StatelessWidget {
  const HoyPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(
      eyebrow: 'Hoy',
      title: 'Jornada',
      body: 'Los consolidados del día se mostrarán aquí cuando el dominio de ventas esté listo.',
    );
  }
}
