package com.officemanagement.ui.components

import androidx.compose.foundation.layout.RowScope
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonColors
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/** Material3's [Button]/[OutlinedButton] hardcode a fully pill-shaped container
 * (`ShapeKeyTokens.CornerFull` resolves straight to `CircleShape`, bypassing the app's
 * `Shapes` theme entirely) — these two force the small 9dp radius frontend/src/App.vue's
 * `button` rule uses instead, so every button in the app matches the web app without
 * every call site repeating `shape = MaterialTheme.shapes.small`. */
@Composable
fun AppButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    colors: ButtonColors = ButtonDefaults.buttonColors(),
    content: @Composable RowScope.() -> Unit,
) {
    Button(onClick = onClick, modifier = modifier, enabled = enabled, shape = MaterialTheme.shapes.small, colors = colors, content = content)
}

@Composable
fun AppOutlinedButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    colors: ButtonColors = ButtonDefaults.outlinedButtonColors(),
    content: @Composable RowScope.() -> Unit,
) {
    OutlinedButton(onClick = onClick, modifier = modifier, enabled = enabled, shape = MaterialTheme.shapes.small, colors = colors, content = content)
}
