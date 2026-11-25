package com.officemanagement.reports

import android.content.Intent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.officemanagement.core.network.ActivityReportRow
import com.officemanagement.core.network.AttendanceReportRow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportsScreen(viewModel: ReportsViewModel = hiltViewModel()) {
    val state = viewModel.uiState
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        viewModel.exportReady.collect { uri ->
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/csv"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            context.startActivity(Intent.createChooser(intent, "Share report"))
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
            SegmentedButton(
                selected = state.reportType == ReportType.ATTENDANCE,
                onClick = { viewModel.selectType(ReportType.ATTENDANCE) },
                shape = SegmentedButtonDefaults.itemShape(0, 2),
            ) { Text("Attendance") }
            SegmentedButton(
                selected = state.reportType == ReportType.ACTIVITY,
                onClick = { viewModel.selectType(ReportType.ACTIVITY) },
                shape = SegmentedButtonDefaults.itemShape(1, 2),
            ) { Text("Activity") }
        }

        Button(
            onClick = viewModel::export,
            enabled = !state.isExporting,
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        ) {
            Text(if (state.isExporting) "Preparing…" else "Export CSV")
        }

        Box(modifier = Modifier.fillMaxSize().padding(top = 12.dp)) {
            when {
                state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                state.error != null -> Column(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(state.error, color = MaterialTheme.colorScheme.error)
                    OutlinedButton(onClick = viewModel::load, modifier = Modifier.padding(top = 12.dp)) {
                        Text("Retry")
                    }
                }
                state.reportType == ReportType.ATTENDANCE -> AttendanceRows(state.attendanceRows)
                else -> ActivityRows(state.activityRows)
            }
        }
    }
}

@Composable
private fun AttendanceRows(rows: List<AttendanceReportRow>) {
    if (rows.isEmpty()) {
        Text("No attendance records in the last 7 days", modifier = Modifier.padding(24.dp))
        return
    }
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(rows) { row ->
            Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                Text(row.employeeName, style = MaterialTheme.typography.titleMedium)
                Row {
                    Text("${row.date ?: ""} · ${row.status}")
                }
            }
            HorizontalDivider()
        }
    }
}

@Composable
private fun ActivityRows(rows: List<ActivityReportRow>) {
    if (rows.isEmpty()) {
        Text("No activity recorded in the last 7 days", modifier = Modifier.padding(24.dp))
        return
    }
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(rows) { row ->
            Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                Text(row.employeeName, style = MaterialTheme.typography.titleMedium)
                Text("${row.date ?: ""} · ${row.activeSeconds / 60}m active · ${row.idleSeconds / 60}m idle")
            }
            HorizontalDivider()
        }
    }
}
