package com.officemanagement.settings

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.AppSettingsItem
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.HolidayItem
import com.officemanagement.core.network.HolidayWriteRequest
import com.officemanagement.core.network.SettingsPatchRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SettingsUiState(
    val isLoading: Boolean = true,
    val settings: AppSettingsItem? = null,
    val holidays: List<HolidayItem> = emptyList(),
    val error: String? = null,
)

/** §35's org-wide config (admin-only) — only the four fields the plan's screen-mapping
 * calls out (weekend days, geofence radius + its enforcement toggle, activity
 * retention, holidays); the backend's AppSettingsSerializer has ~15 more (agent
 * intervals, split-shift/half-day-leave toggles, ...) that belong to whichever later
 * phase actually needs to edit them. */
@HiltViewModel
class SettingsViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var uiState by mutableStateOf(SettingsUiState())
        private set

    init {
        load()
    }

    fun load() {
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            uiState = try {
                val settings = api.settings()
                val holidays = api.holidays().results
                SettingsUiState(isLoading = false, settings = settings, holidays = holidays)
            } catch (e: Exception) {
                SettingsUiState(isLoading = false, error = e.message ?: "Could not load settings.")
            }
        }
    }

    fun toggleWeekendDay(day: Int) {
        val current = uiState.settings ?: return
        val days = if (day in current.weekendDays) current.weekendDays - day else current.weekendDays + day
        save(SettingsPatchRequest(weekendDays = days))
    }

    fun setRadius(radiusMeters: Int) = save(SettingsPatchRequest(radiusMeters = radiusMeters))

    fun setRequireInsideRadius(required: Boolean) = save(SettingsPatchRequest(requireCheckInInsideRadius = required))

    fun setRetentionDays(days: Int) = save(SettingsPatchRequest(activityRetentionDays = days))

    private fun save(patch: SettingsPatchRequest) {
        viewModelScope.launch {
            try {
                uiState = uiState.copy(settings = api.updateSettings(patch))
            } catch (e: Exception) {
                uiState = uiState.copy(error = e.message ?: "That change didn't save.")
            }
        }
    }

    fun addHoliday(date: String, name: String) {
        viewModelScope.launch {
            try {
                api.createHoliday(HolidayWriteRequest(date = date, name = name))
                uiState = uiState.copy(holidays = api.holidays().results)
            } catch (_: Exception) {
                // The add-holiday form stays as typed on failure.
            }
        }
    }

    fun deleteHoliday(id: Int) {
        viewModelScope.launch {
            try {
                api.deleteHoliday(id)
                uiState = uiState.copy(holidays = uiState.holidays.filterNot { it.id == id })
            } catch (_: Exception) {
                // Reverts to the server's view on next load().
            }
        }
    }
}
