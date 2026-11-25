package com.officemanagement.core.data

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Holds the one bearer token this install has (see accounts.authentication.
 * BearerTokenAuthentication on the backend) in Keystore-backed encrypted storage.
 *
 * No plaintext fallback: if EncryptedSharedPreferences/Keystore access fails, this
 * throws rather than degrading to a plain file — the same "no disk fallback for the
 * secret" rule desktop-agent/agent/config.py applies to the desktop agent's device
 * token. The token is also the one thing excluded from Android backups (see
 * res/xml/backup_rules.xml and data_extraction_rules.xml).
 */
@Singleton
class TokenStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context,
        "auth_token_store",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    private val _token = MutableStateFlow(prefs.getString(KEY_TOKEN, null))

    /** Null means logged out — every screen that needs auth observes this directly
     * rather than polling, so a logout (or a revoked token, see AuthRepository) is
     * reflected everywhere at once, including the background tracking worker (§8 of
     * the plan): it shares this same token, so finding none here is what makes
     * "logged out" and "tracking paused" the same state rather than two to keep in
     * sync. */
    val token: StateFlow<String?> = _token.asStateFlow()

    fun save(token: String) {
        prefs.edit().putString(KEY_TOKEN, token).apply()
        _token.value = token
    }

    fun clear() {
        prefs.edit().remove(KEY_TOKEN).apply()
        _token.value = null
    }

    private companion object {
        const val KEY_TOKEN = "auth_token"
    }
}
