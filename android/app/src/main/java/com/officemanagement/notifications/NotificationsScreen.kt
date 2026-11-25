package com.officemanagement.notifications
import com.officemanagement.ui.components.AppOutlinedButton
import com.officemanagement.ui.components.AppButton

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.NotificationItem

@Composable
fun NotificationsScreen(viewModel: NotificationsViewModel = hiltViewModel()) {
    val state = viewModel.uiState

    Box(modifier = Modifier.fillMaxSize()) {
        when {
            state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            state.error != null -> Column(
                modifier = Modifier.align(Alignment.Center).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(state.error, color = MaterialTheme.colorScheme.error)
                AppOutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                    Text("Retry")
                }
            }
            state.items.isEmpty() -> Text(
                "No notifications",
                modifier = Modifier.align(Alignment.Center),
                style = MaterialTheme.typography.bodyLarge,
            )
            else -> Column(modifier = Modifier.fillMaxSize()) {
                AppButton(
                    onClick = viewModel::markAllRead,
                    modifier = Modifier.padding(16.dp).fillMaxWidth(),
                ) {
                    Text("Mark all read")
                }
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(state.items, key = { it.id }) { item ->
                        NotificationRow(item, onClick = { viewModel.markRead(item.id) })
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationRow(item: NotificationItem, onClick: () -> Unit) {
    val isUnread = item.readAt == null
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(enabled = isUnread, onClick = onClick)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            item.message,
            fontWeight = if (isUnread) FontWeight.Bold else FontWeight.Normal,
        )
        Text(item.createdAt, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
