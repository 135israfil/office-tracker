package com.officemanagement.auth

import com.officemanagement.core.data.TokenStore
import com.officemanagement.core.network.ApiErrorBody
import com.officemanagement.core.network.ApiService
import com.officemanagement.core.network.CurrentUser
import com.officemanagement.core.network.TokenLoginRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val api: ApiService,
    private val tokenStore: TokenStore,
    private val json: Json,
) {
    /** Null until the first successful login or refreshCurrentUser() this process —
     * a fresh app start with a saved token still shows nothing until that completes. */
    private val _currentUser = MutableStateFlow<CurrentUser?>(null)
    val currentUser: StateFlow<CurrentUser?> = _currentUser.asStateFlow()

    val token: StateFlow<String?> = tokenStore.token

    suspend fun login(email: String, password: String): Result<CurrentUser> =
        try {
            val response = api.login(TokenLoginRequest(email, password))
            tokenStore.save(response.token)
            _currentUser.value = response.user
            Result.success(response.user)
        } catch (e: HttpException) {
            Result.failure(Exception(errorDetail(e)))
        } catch (e: Exception) {
            Result.failure(e)
        }

    /** Best-effort: the token is cleared locally either way, so a dead network
     * connection never traps someone in a logged-in state they asked to leave. */
    suspend fun logout() {
        try {
            api.revokeToken()
        } catch (_: Exception) {
            // Ignored on purpose — see docstring.
        }
        tokenStore.clear()
        _currentUser.value = null
    }

    /** Called once at app start when a saved token exists, to learn who it belongs to
     * (and to notice a token that's since been revoked server-side, e.g. by an admin
     * disabling the account). */
    suspend fun refreshCurrentUser() {
        if (tokenStore.token.value == null) return
        try {
            _currentUser.value = api.me()
        } catch (e: HttpException) {
            if (e.code() == 401) {
                tokenStore.clear()
                _currentUser.value = null
            }
        } catch (_: Exception) {
            // A transient network failure leaves the stale currentUser in place rather
            // than logging someone out just because they walked out of signal range.
        }
    }

    private fun errorDetail(e: HttpException): String {
        val body = e.response()?.errorBody()?.string()
        val detail = body?.let { runCatching { json.decodeFromString<ApiErrorBody>(it).detail }.getOrNull() }
        return detail ?: "Something went wrong (${e.code()}). Please try again."
    }
}
