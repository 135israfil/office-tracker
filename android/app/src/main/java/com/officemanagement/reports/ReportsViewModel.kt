package com.officemanagement.reports

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ActivityReportRow
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.AttendanceReportRow
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import javax.inject.Inject

enum class ReportType { ATTENDANCE, ACTIVITY }

data class ReportsUiState(
    val reportType: ReportType = ReportType.ATTENDANCE,
    val isLoading: Boolean = true,
    val attendanceRows: List<AttendanceReportRow> = emptyList(),
    val activityRows: List<ActivityReportRow> = emptyList(),
    val error: String? = null,
    val isExporting: Boolean = false,
)

/** §25/§26's reports (admin-only) — a fixed 7-day window in this phase (the web app's
 * date-range picker and department/status filters are a later phase, see the plan's
 * screen-mapping notes); CSV export shares the file via a share-sheet intent rather
 * than Storage Access Framework's CreateDocument flow, since there's no "Downloads"
 * folder convention to replicate on Android the way there is in a desktop browser. */
@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val api: ApiService,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    var uiState by mutableStateOf(ReportsUiState())
        private set

    private val _exportReady = MutableSharedFlow<android.net.Uri>(extraBufferCapacity = 1)
    val exportReady: SharedFlow<android.net.Uri> = _exportReady

    private val dateFrom: String = LocalDate.now().minusDays(6).format(DateTimeFormatter.ISO_DATE)
    private val dateTo: String = LocalDate.now().format(DateTimeFormatter.ISO_DATE)
    private val filters: Map<String, String> get() = mapOf("date_from" to dateFrom, "date_to" to dateTo)

    init {
        load()
    }

    fun selectType(type: ReportType) {
        if (type == uiState.reportType) return
        uiState = uiState.copy(reportType = type)
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                when (uiState.reportType) {
                    ReportType.ATTENDANCE -> uiState.copy(
                        isLoading = false,
                        attendanceRows = api.attendanceReport(filters).rows,
                    )
                    ReportType.ACTIVITY -> uiState.copy(
                        isLoading = false,
                        activityRows = api.activityReport(filters).rows,
                    )
                }
            } catch (e: Exception) {
                uiState.copy(isLoading = false, error = e.message ?: "Could not load the report.")
            }
        }
    }

    fun export() {
        uiState = uiState.copy(isExporting = true)
        viewModelScope.launch {
            try {
                val reportName = if (uiState.reportType == ReportType.ATTENDANCE) "attendance" else "activity"
                val body = api.exportReport(reportName, filters + ("format" to "csv"))
                val exportsDir = File(context.cacheDir, "exports").apply { mkdirs() }
                val file = File(exportsDir, "$reportName-$dateFrom-to-$dateTo.csv")
                file.outputStream().use { out -> body.byteStream().use { it.copyTo(out) } }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                _exportReady.emit(uri)
            } catch (_: Exception) {
                // The export button becoming available again is the only feedback this
                // phase gives on failure — a toast/snackbar is a small follow-up, not
                // worth a new UI pattern for one button.
            } finally {
                uiState = uiState.copy(isExporting = false)
            }
        }
    }
}
