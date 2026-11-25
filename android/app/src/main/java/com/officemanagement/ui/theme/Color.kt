package com.officemanagement.ui.theme

import androidx.compose.ui.graphics.Color

// Lifted straight from frontend/src/App.vue's :root palette, so the app reads as the
// same product as the web client rather than a reskin of stock Material3. The web app
// has no dark variant to parallel, so this is the only palette — see Theme.kt.
val Bg = Color(0xFFF6F7F9)
val Surface = Color(0xFFFFFFFF)
val SurfaceSunken = Color(0xFFF8F9FB)
val Border = Color(0xFFE8EAEF)
val BorderStrong = Color(0xFFD3D8E0)

val TextPrimary = Color(0xFF14161A)
val TextSoft = Color(0xFF454B56)
val Muted = Color(0xFF767D8B)

val Accent = Color(0xFF3B5BDB)
val AccentHover = Color(0xFF304EC2)
val AccentSoft = Color(0xFFEEF2FF)

val Ok = Color(0xFF0B7A4B)
val OkSoft = Color(0xFFE9F9F1)
val OkBorder = Color(0xFFA9E5C8)

val Danger = Color(0xFFB5241C)
val DangerSoft = Color(0xFFFDF1F0)
val DangerBorder = Color(0xFFF5C4C0)

val Warn = Color(0xFFA55A06)
val WarnSoft = Color(0xFFFDF6E8)
val WarnBorder = Color(0xFFF3D9A4)
