package com.officemanagement.attendance

import android.content.Context
import android.location.Location
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import javax.inject.Singleton

/** A single current-location fix for a check-in/out punch — not continuous tracking.
 * Returns null on any failure (permission not granted, no fix available, timeout)
 * rather than throwing, matching how the rest of this app degrades a collector
 * failure to an honest empty value instead of crashing a screen over it. */
@Singleton
class LocationProvider @Inject constructor(@ApplicationContext context: Context) {

    private val client = LocationServices.getFusedLocationProviderClient(context)

    suspend fun currentLocation(): Location? = suspendCancellableCoroutine { continuation ->
        try {
            client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
                .addOnSuccessListener { location -> continuation.resume(location) }
                .addOnFailureListener { continuation.resume(null) }
        } catch (_: SecurityException) {
            // Permission was revoked between the caller's check and this call.
            continuation.resume(null)
        }
    }
}
