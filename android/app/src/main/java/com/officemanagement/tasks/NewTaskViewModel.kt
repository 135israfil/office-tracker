package com.officemanagement.tasks

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.EmployeeStub
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Backs the New Task dialog's assignee checklist — the same minimal, non-admin-safe
 * directory (id/employee_id/name only) backend/tasks/views.py's AssignableEmployeesView
 * was built for, not the full admin Employees directory. */
@HiltViewModel
class NewTaskViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    var employees by mutableStateOf<List<EmployeeStub>>(emptyList())
        private set

    init {
        viewModelScope.launch {
            employees = try {
                api.assignableEmployees()
            } catch (_: Exception) {
                emptyList()
            }
        }
    }
}
