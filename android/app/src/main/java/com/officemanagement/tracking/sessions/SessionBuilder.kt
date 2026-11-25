package com.officemanagement.tracking.sessions

import java.time.Duration
import java.time.Instant
import java.util.UUID

/** Turns a stream of [Sample]s into closed, bounded intervals (§18) — a Kotlin port of
 * desktop-agent/agent/sessions.py's `SessionBuilder`, ported rule-for-rule so the two
 * stay provably equivalent (see SessionBuilderTest, which mirrors
 * desktop-agent/tests/test_sessions.py's cases one-to-one).
 *
 * Four rules decide when an interval ends, exactly as on desktop:
 * 1. The value changed (a different app, or active becoming idle).
 * 2. Going idle closes the application track too.
 * 3. A hard cap ([maxSessionSeconds]) splits a long-running session so a crash loses at
 *    most the current interval.
 * 4. A gap in samples ([maxSampleGapSeconds]) closes at the *last* sample, not at
 *    resumption — unobserved time is not usage.
 *
 * Pure: no clock of its own, no I/O. `websiteDomain` is carried through for fidelity
 * with the desktop port even though nothing on this platform populates it yet (no
 * browser-tab reading on Android in this phase) — a WEBSITE session simply never gets
 * produced, the same honest absence as an app with no foreground window.
 */
class SessionBuilder(
    private val maxSessionSeconds: Long = MAX_SESSION_SECONDS,
    private val maxSampleGapSeconds: Long = MAX_SAMPLE_GAP_SECONDS,
) {
    private data class OpenSession(
        val activityType: String,
        val startTime: Instant,
        val applicationName: String = "",
        val executableName: String = "",
        val websiteDomain: String = "",
        // Assigned at creation, not at upload — the same reasoning as the desktop
        // port: the id has to survive a crash between the two for the server's
        // idempotent upsert to mean anything.
        val clientEventId: String = UUID.randomUUID().toString(),
    ) {
        fun key(): List<String> = listOf(activityType, applicationName, executableName, websiteDomain)

        fun close(at: Instant): ClosedSession {
            val end = if (at.isAfter(startTime)) at else startTime
            return ClosedSession(
                clientEventId = clientEventId,
                activityType = activityType,
                applicationName = applicationName,
                executableName = executableName,
                websiteDomain = websiteDomain,
                startTime = startTime.toString(),
                endTime = end.toString(),
                durationSeconds = Duration.between(startTime, end).seconds,
            )
        }
    }

    private val open = linkedMapOf<String, OpenSession>()
    private var lastSampleAt: Instant? = null

    /** Used by status displays and tests — which track is open, and as what type. */
    val openTracks: Map<String, String>
        get() = open.mapValues { (_, session) -> session.activityType }

    fun observe(sample: Sample): List<ClosedSession> {
        val closed = mutableListOf<ClosedSession>()

        val last = lastSampleAt
        if (last != null) {
            val gap = Duration.between(last, sample.at).seconds
            if (gap > maxSampleGapSeconds || gap < 0) {
                // Rule 4, and the same branch handles a clock that stepped backwards:
                // in both cases the open sessions describe a period we can no longer
                // vouch for, so they end where observation actually stopped.
                closed += closeAll(last)
            }
        }
        lastSampleAt = sample.at

        val wanted = wantedSessions(sample)
        for (track in TRACKS) {
            closed += reconcile(track, wanted[track], sample.at)
        }

        return closed.filter { it.durationSeconds >= MIN_SESSION_SECONDS }
    }

    /** Close everything — on shutdown, on the kill switch, before a long pause. */
    fun flush(at: Instant): List<ClosedSession> {
        val closed = closeAll(at)
        lastSampleAt = null
        return closed.filter { it.durationSeconds >= MIN_SESSION_SECONDS }
    }

    private fun wantedSessions(sample: Sample): Map<String, OpenSession?> {
        val state = OpenSession(
            activityType = if (sample.isIdle) TYPE_IDLE else TYPE_ACTIVE,
            startTime = sample.at,
        )

        // Rule 2: no application track while idle, and none when there is no
        // foreground app to attribute time to.
        val application = if (!sample.isIdle && sample.hasApp) {
            OpenSession(
                activityType = TYPE_APPLICATION,
                startTime = sample.at,
                applicationName = sample.applicationName,
                executableName = sample.executableName,
            )
        } else {
            null
        }

        val website = if (!sample.isIdle && sample.websiteDomain.isNotEmpty()) {
            OpenSession(
                activityType = TYPE_WEBSITE,
                startTime = sample.at,
                websiteDomain = sample.websiteDomain,
            )
        } else {
            null
        }

        return mapOf(TRACK_STATE to state, TRACK_APPLICATION to application, TRACK_WEBSITE to website)
    }

    private fun reconcile(track: String, wanted: OpenSession?, at: Instant): List<ClosedSession> {
        val current = open[track]
        val closed = mutableListOf<ClosedSession>()

        if (current != null && wanted != null && current.key() == wanted.key()) {
            if (Duration.between(current.startTime, at).seconds >= maxSessionSeconds) {
                // Rule 3: same value, but long enough that leaving it open risks
                // losing it. Close and immediately reopen.
                closed += current.close(at)
                open[track] = OpenSession(
                    activityType = current.activityType,
                    startTime = at,
                    applicationName = current.applicationName,
                    executableName = current.executableName,
                    websiteDomain = current.websiteDomain,
                )
            }
            return closed
        }

        if (current != null) {
            closed += current.close(at)
            open.remove(track)
        }

        if (wanted != null) {
            open[track] = wanted
        }
        return closed
    }

    private fun closeAll(at: Instant): List<ClosedSession> {
        val closed = open.values.map { it.close(at) }
        open.clear()
        return closed
    }

    companion object {
        const val TYPE_ACTIVE = "ACTIVE"
        const val TYPE_IDLE = "IDLE"
        const val TYPE_APPLICATION = "APPLICATION"
        const val TYPE_WEBSITE = "WEBSITE"

        private const val TRACK_STATE = "state"
        private const val TRACK_APPLICATION = "application"
        private const val TRACK_WEBSITE = "website"
        private val TRACKS = listOf(TRACK_STATE, TRACK_APPLICATION, TRACK_WEBSITE)

        // Rule 3. Matches the desktop agent's figure exactly.
        const val MAX_SESSION_SECONDS = 15L * 60

        // Rule 4. Matches the desktop agent's figure exactly.
        const val MAX_SAMPLE_GAP_SECONDS = 60L

        // Below this, an interval is an artefact of sampling rather than a fact about
        // the day.
        const val MIN_SESSION_SECONDS = 1L
    }
}
