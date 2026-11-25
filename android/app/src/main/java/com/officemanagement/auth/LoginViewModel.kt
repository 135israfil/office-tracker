package com.officemanagement.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class LoginViewModel @Inject constructor(private val authRepository: AuthRepository) : ViewModel() {

    var uiState by mutableStateOf(LoginUiState())
        private set

    fun onEmailChange(value: String) {
        uiState = uiState.copy(email = value, error = null)
    }

    fun onPasswordChange(value: String) {
        uiState = uiState.copy(password = value, error = null)
    }

    /** No onSuccess callback: AppNavGraph reacts to AuthRepository's own state once
     * this returns, rather than being told to navigate. */
    fun login() {
        if (uiState.email.isBlank() || uiState.password.isBlank()) {
            uiState = uiState.copy(error = "Enter your email and password.")
            return
        }
        uiState = uiState.copy(isLoading = true, error = null)
        viewModelScope.launch {
            val result = authRepository.login(uiState.email.trim(), uiState.password)
            uiState = result.fold(
                onSuccess = { LoginUiState() },
                onFailure = { uiState.copy(isLoading = false, error = it.message) },
            )
        }
    }
}
