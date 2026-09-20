import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lumo/lumo/tokens.dart';

class LumoTypography {
  static TextStyle inter({
    required double size,
    FontWeight weight = FontWeight.w400,
    double height = 1.5,
    double letterSpacing = 0,
    Color? color,
  }) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: weight,
      height: height,
      letterSpacing: letterSpacing,
      color: color ?? LumoColors.foreground,
    );
  }

  static TextStyle instrumentSerif({
    required double size,
    FontWeight weight = FontWeight.w400,
    FontStyle style = FontStyle.normal,
    double height = 1.25,
    double letterSpacing = 0,
    Color? color,
  }) {
    return GoogleFonts.instrumentSerif(
      fontSize: size,
      fontWeight: weight,
      fontStyle: style,
      height: height,
      letterSpacing: letterSpacing,
      color: color ?? LumoColors.foreground,
    );
  }

  static TextStyle get displayGreeting => instrumentSerif(
        size: 34,
        style: FontStyle.italic,
        height: 1.05,
        letterSpacing: -0.85,
      );

  static TextStyle get titleSerifLg => instrumentSerif(size: 32);

  static TextStyle get titleSerifMd => instrumentSerif(size: 26);

  static TextStyle get eyebrow => inter(
        size: 11,
        letterSpacing: 1.98,
        color: LumoColors.mutedForeground,
      );

  static TextStyle get sectionLabel => inter(
        size: 11,
        letterSpacing: 0.55,
        color: LumoColors.mutedForeground,
      );

  static TextStyle get body => inter(
        size: 15,
        height: 1.625,
        color: LumoColors.foreground.withValues(alpha: 0.9),
      );

  static TextStyle get cardTitle => inter(size: 14, weight: FontWeight.w500);

  static TextStyle get cardTitleStrong => inter(size: 16, weight: FontWeight.w600);

  static TextStyle get metricHero => inter(
        size: 36,
        weight: FontWeight.w600,
        height: 1.0,
        letterSpacing: -0.9,
      );

  static TextStyle get metricLg => inter(size: 20, weight: FontWeight.w600);

  static TextStyle get metricSm => inter(size: 14, weight: FontWeight.w600);

  static TextStyle get fieldValue => inter(size: 16, weight: FontWeight.w500);

  static TextStyle get caption => inter(size: 12, color: LumoColors.mutedForeground);

  static TextStyle get captionMicro => inter(size: 10, color: LumoColors.mutedForeground);

  static TextStyle get buttonPrimary => inter(
        size: 14,
        weight: FontWeight.w500,
        color: LumoColors.primaryForeground,
      );

  static TextStyle get buttonSecondary => inter(
        size: 14,
        color: LumoColors.foreground.withValues(alpha: 0.8),
      );

  static TextStyle get chip => inter(
        size: 12,
        color: LumoColors.foreground.withValues(alpha: 0.8),
      );

  static TextStyle get statusChip => inter(
        size: 11,
        weight: FontWeight.w500,
        color: LumoColors.accentForeground,
      );

  static TextStyle get navLabel => inter(size: 11, color: LumoColors.mutedForeground);

  static TextStyle get navLabelActive => navLabel.copyWith(
        fontWeight: FontWeight.w500,
        color: LumoColors.foreground,
      );

  static TextStyle get input => inter(size: 14);

  static TextStyle get interBold => inter(size: 14, weight: FontWeight.w700);
}
