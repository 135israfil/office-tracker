package com.officemanagement.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.officemanagement.ui.theme.Danger
import com.officemanagement.ui.theme.DangerBorder
import com.officemanagement.ui.theme.DangerSoft
import com.officemanagement.ui.theme.Ok
import com.officemanagement.ui.theme.OkBorder
import com.officemanagement.ui.theme.OkSoft
import com.officemanagement.ui.theme.Warn
import com.officemanagement.ui.theme.WarnBorder
import com.officemanagement.ui.theme.WarnSoft

enum class BadgeTone { OK, WARN, DANGER, NEUTRAL }

/** Matches frontend/src/App.vue's `.badge` — a small pill with a soft tinted background,
 * used everywhere a screen shows one-word status (active/inactive, present/late/absent,
 * online/idle/offline). */
@Composable
fun StatusBadge(text: String, tone: BadgeTone, modifier: Modifier = Modifier) {
    val (bg, fg, border) = when (tone) {
        BadgeTone.OK -> Triple(OkSoft, Ok, OkBorder)
        BadgeTone.WARN -> Triple(WarnSoft, Warn, WarnBorder)
        BadgeTone.DANGER -> Triple(DangerSoft, Danger, DangerBorder)
        // Matches the web app's `.badge` with no tone class (e.g. a task's TODO status):
        // transparent background and border, just the padded pill shape.
        BadgeTone.NEUTRAL -> Triple(Color.Transparent, MaterialTheme.colorScheme.onSurface, Color.Transparent)
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = bg,
        contentColor = fg,
        border = BorderStroke(1.dp, border),
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp),
        )
    }
}
