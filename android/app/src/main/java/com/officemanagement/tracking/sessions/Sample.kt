package com.officemanagement.tracking.sessions

import java.time.Instant

/** One reading fed to [SessionBuilder] — the mobile analogue of desktop-agent's
 * `agent.sessions.Sample`. Unlike the desktop agent, which samples continuously every
 * couple of seconds, the mobile collector only ever has point-in-time foreground-app
 * events to feed this from (see `tracking/collector/CollectorWorker.kt`) — the builder
 * itself does not care how often it is fed, only that each Sample's timestamp is real.
 *
 * There is no idle state on this platform (phones have no equivalent of
 * GetLastInputInfo/CGEventSourceSecondsSinceLastEventType without an Accessibility
 * Service): every Sample the mobile collector produces is ONLINE, and a phone that
 * nobody is touching simply produces no samples at all, which the gap rule below
 * already treats as unobserved time — the same honest answer, reached a different way.
 */
data class Sample(
    val at: Instant,
    val state: String = STATE_ONLINE,
    val applicationName: String = "",
    val executableName: String = "",
    val websiteDomain: String = "",
) {
    val isIdle: Boolean get() = state == STATE_IDLE
    val hasApp: Boolean get() = applicationName.isNotEmpty() || executableName.isNotEmpty()

    companion object {
        const val STATE_ONLINE = "ONLINE"
        const val STATE_IDLE = "IDLE"
    }
}

/** One closed interval, shaped to serialize directly as the body
 * `ActivitySessionSerializer` (backend/activities/serializers.py) expects — the same
 * four fields the desktop agent's `_OpenSession.close()` produces, minus
 * `duration_seconds`, which the server derives from the two timestamps rather than
 * trusting a client-supplied one. */
data class ClosedSession(
    val clientEventId: String,
    val activityType: String,
    val applicationName: String = "",
    val executableName: String = "",
    val websiteDomain: String = "",
    val startTime: String,
    val endTime: String,
    val durationSeconds: Long,
)
