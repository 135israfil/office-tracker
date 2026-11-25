package com.officemanagement.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// frontend/src/App.vue has no dark palette to parallel, so this app shows the same one
// scheme regardless of system theme rather than inventing a dark variant nobody designed.
private val Colors = lightColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    primaryContainer = AccentSoft,
    onPrimaryContainer = Accent,
    secondary = AccentHover,
    onSecondary = Color.White,
    // NavigationDrawerItem's selected state reads secondaryContainer/onSecondaryContainer
    // by default — matching these to the accent pair is what makes the selected drawer
    // row come out looking like App.vue's `.navlink.router-link-active` for free.
    secondaryContainer = AccentSoft,
    onSecondaryContainer = Accent,
    background = Bg,
    onBackground = TextPrimary,
    surface = Surface,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceSunken,
    onSurfaceVariant = Muted,
    outline = BorderStrong,
    outlineVariant = Border,
    error = Danger,
    onError = Color.White,
    errorContainer = DangerSoft,
    onErrorContainer = Danger,
    // M3's tonal elevation tints elevated surfaces (Card, Menu, ...) with `surfaceTint`
    // (= primary by default), which is why an out-of-the-box Card came out faint lavender
    // instead of white — the web app has no such tint, just a plain box-shadow.
    surfaceTint = Color.Transparent,
)

// --radius-sm (9px) / --radius (14px) from App.vue; pill shapes (chips/badges) are built
// locally with a 50% corner percent rather than through this scale.
private val Shapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(9.dp),
    medium = RoundedCornerShape(14.dp),
    large = RoundedCornerShape(14.dp),
    extraLarge = RoundedCornerShape(20.dp),
)

@Composable
fun OfficeManagementTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, typography = Typography, shapes = Shapes, content = content)
}
