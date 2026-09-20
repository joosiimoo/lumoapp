import 'package:flutter/material.dart';

class LumoColors {
  static const background = Color(0xFFFCFAF4);
  static const surface = Color(0xFFFCFAF4);
  static const surfaceElevated = Color(0xFFFFFFFF);
  static const foreground = Color(0xFF0A140E);
  static const mutedForeground = Color(0xFF5C675D);
  static const primary = Color(0xFF267B4C);
  static const primaryForeground = Color(0xFFFCFAF4);
  static const secondary = Color(0xFFF1F3EB);
  static const secondaryForeground = Color(0xFF0F1F14);
  static const muted = Color(0xFFEFEFE9);
  static const accent = Color(0xFFDAF2E6);
  static const accentForeground = Color(0xFF032110);
  static const border = Color(0xFFE3E6DE);
  static const input = Color(0xFFEAECE5);
  static const ring = Color(0xFF84BBAF);
  static const destructive = Color(0xFFDE3B3D);
  static const user = Color(0xFF267B4C);
  static const userForeground = Color(0xFFFCFAF4);
  static const attention = Color(0xFFD79628);
  static const attentionSoft = Color(0xFFFAE6BB);
  static const lumoTeal = Color(0xFF78D7D6);
  static const lumoLavender = Color(0xFFB1B0EF);
  static const markCore = Color(0xFF042C43);
}

class LumoGradients {
  static const lumoText = [
    Color(0xFF36BABA),
    Color(0xFF5EADE2),
    Color(0xFFAE96DA),
  ];
  static const lumoFill = [
    Color(0xFF5ECBCB),
    Color(0xFF80A5E3),
    Color(0xFFAE96DA),
  ];
  static const markRing = [Color(0xFF5ECBCB), Color(0xFF9794E0)];

  static const lumoFillGradient = LinearGradient(
    begin: Alignment(-0.98, -0.17),
    end: Alignment(0.98, 0.17),
    colors: lumoFill,
    stops: [0.0, 0.55, 1.0],
  );

  static const lumoTextGradient = LinearGradient(
    begin: Alignment(-0.98, -0.17),
    end: Alignment(0.98, 0.17),
    colors: lumoText,
    stops: [0.0, 0.45, 1.0],
  );
}

class LumoSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const smPlus = 10.0;
  static const md = 12.0;
  static const mdPlus = 14.0;
  static const lg = 16.0;
  static const xl = 20.0;
  static const xxl = 24.0;
  static const xxxl = 32.0;
  static const screenPaddingH = 16.0;
  static const headerPaddingH = 20.0;
  static const streamGap = 16.0;
  static const listGap = 10.0;
  static const gridGap = 12.0;
  static const groupGap = 24.0;
  static const cardPaddingStdH = 16.0;
  static const cardPaddingStdV = 14.0;
  static const cardPaddingLgH = 20.0;
  static const cardPaddingLgV = 16.0;
  static const cardPaddingHero = 20.0;
}

class LumoRadius {
  static const sm = 12.0;
  static const md = 14.0;
  static const lg = 16.0;
  static const xl = 20.0;
  static const xxl = 24.0;
  static const xxxl = 28.0;
  static const xxxxl = 32.0;
  static const pill = 999.0;
  static const card = 24.0;
  static const userBubble = 28.0;
  static const thumb = 20.0;
  static const actionCard = 24.0;
}

class LumoShadows {
  static const softCard = [
    BoxShadow(offset: Offset(0, 1), color: Color(0x80DDDFD8)),
    BoxShadow(offset: Offset(0, 8), blurRadius: 30, spreadRadius: -18, color: Color(0x2631503C)),
  ];
  static const ringLumo = [
    BoxShadow(offset: Offset.zero, spreadRadius: 1, color: Color(0x66A8D9D8)),
    BoxShadow(offset: Offset(0, 6), blurRadius: 24, spreadRadius: -12, color: Color(0x5961AAC1)),
  ];
  static const small = [
    BoxShadow(offset: Offset(0, 1), blurRadius: 2, color: Color(0x0D000000)),
  ];
}

class LumoSizes {
  static const contentMaxWidth = 420.0;
  static const designWidth = 390.0;
  static const composerHeight = 44.0;
  static const composerIconButton = 32.0;
  static const sendButton = 36.0;
  static const navPillWidth = 56.0;
  static const navPillHeight = 36.0;
  static const navIcon = 20.0;
  static const navBarHeight = 64.0;
  static const markSm = 14.0;
  static const markMd = 18.0;
  static const markLg = 20.0;
  static const primaryButtonHeight = 48.0;
  static const inCardButtonHeight = 40.0;
  static const chipHeight = 28.0;
  static const statusChipHeight = 20.0;
  static const thumbSm = 36.0;
  static const thumbMd = 40.0;
  static const chartHeight = 96.0;
  static const chartBarGap = 6.0;
  static const chartMinBar = 0.08;
}

class LumoMotion {
  static const duration = Duration(milliseconds: 150);
  static const curve = Cubic(0.4, 0.0, 0.2, 1.0);
}
