package com.officemanagement.core.network

import com.officemanagement.core.data.TokenStore
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/** Adds `Authorization: Bearer <token>` to every request once logged in — the same
 * token the background tracking worker (§8 of the plan) will eventually use too, so
 * there is exactly one place either of them needs to look. */
class AuthInterceptor @Inject constructor(private val tokenStore: TokenStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = tokenStore.token.value
        val request = chain.request().let {
            if (token == null) it else it.newBuilder().addHeader("Authorization", "Bearer $token").build()
        }
        return chain.proceed(request)
    }
}
