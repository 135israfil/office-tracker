package com.officemanagement.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.googlefonts.Font as GoogleFontRef
import androidx.compose.ui.text.googlefonts.GoogleFont
import androidx.compose.ui.unit.sp
import com.officemanagement.R

// The Google Fonts provider cert — the same boilerplate Android's own docs ship, not
// anything project-specific. Lets Inter download on-device instead of shipping font
// binaries, matching `@import "@fontsource-variable/inter"` in frontend/src/App.vue.
private val fontProvider = GoogleFont.Provider(
    providerAuthority = "com.google.android.gms.fonts",
    providerPackage = "com.google.android.gms",
    certificates = R.array.com_google_android_gms_fonts_certs,
)

private val interFont = GoogleFont("Inter")

private fun inter(weight: FontWeight) = FontFamily(
    GoogleFontRef(googleFont = interFont, fontProvider = fontProvider, weight = weight),
)

private val InterRegular = inter(FontWeight.Normal)
private val InterMedium = inter(FontWeight.Medium)
private val InterSemiBold = inter(FontWeight.SemiBold)
private val InterBold = inter(FontWeight.Bold)

// font-variant-numeric: tabular-nums in App.vue — this app is full of durations, counts
// and clock times that should line up in a column the same way.
private val tabularNums = PlatformTextStyle(includeFontPadding = false)

private fun style(family: FontFamily, size: Int, weight: FontWeight, tracking: Double = 0.0) = TextStyle(
    fontFamily = family,
    fontSize = size.sp,
    fontWeight = weight,
    letterSpacing = tracking.sp,
    platformStyle = tabularNums,
)

// Sized straight off frontend/src/App.vue's h2/h3/h4/body/.stat rules (1rem = 16sp).
val Typography = Typography(
    headlineSmall = style(InterSemiBold, 22, FontWeight.SemiBold, -0.4),
    titleLarge = style(InterSemiBold, 20, FontWeight.SemiBold, -0.3),
    titleMedium = style(InterSemiBold, 16, FontWeight.SemiBold, -0.2),
    titleSmall = style(InterSemiBold, 15, FontWeight.SemiBold, -0.2),
    bodyLarge = style(InterRegular, 15, FontWeight.Normal),
    bodyMedium = style(InterRegular, 14, FontWeight.Normal),
    bodySmall = style(InterRegular, 13, FontWeight.Normal),
    labelLarge = style(InterMedium, 14, FontWeight.Medium),
    labelMedium = style(InterMedium, 13, FontWeight.Medium),
    labelSmall = style(InterBold, 11, FontWeight.Bold, 0.6),
)
