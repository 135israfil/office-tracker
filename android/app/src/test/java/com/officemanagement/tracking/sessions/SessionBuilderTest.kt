package com.officemanagement.tracking.sessions

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/** Mirrors desktop-agent/tests/test_sessions.py's TestSessionBuilder one-to-one — the
 * self-check the plan's §8.7 asks for, proving this port produces the same closed
 * sessions as the Python original for the same fixed sample sequences. */
class SessionBuilderTest {

    private val start: Instant = Instant.parse("2026-08-19T09:00:00Z")
    private fun at(seconds: Long): Instant = start.plusSeconds(seconds)

    private val vscode = Pair("Visual Studio Code", "com.vscode")
    private val chrome = Pair("Google Chrome", "com.chrome")

    private fun sample(
        seconds: Long,
        state: String = Sample.STATE_ONLINE,
        app: Pair<String, String>? = vscode,
    ) = Sample(
        at = at(seconds),
        state = state,
        applicationName = app?.first ?: "",
        executableName = app?.second ?: "",
    )

    private fun byType(sessions: List<ClosedSession>): Map<String, ClosedSession> =
        sessions.associateBy { it.activityType }

    /** Drives the builder a reading every couple of seconds, the way the collector's
     * reconstructed event stream does — jumping straight from t=0 to t=120 would trip
     * the sample-gap rule and prove nothing about app switching. */
    private fun feed(
        builder: SessionBuilder,
        startSeconds: Long,
        endSeconds: Long,
        step: Long = 2,
        state: String = Sample.STATE_ONLINE,
        app: Pair<String, String>? = vscode,
    ): List<ClosedSession> {
        val closed = mutableListOf<ClosedSession>()
        var moment = startSeconds
        while (moment <= endSeconds) {
            closed += builder.observe(
                Sample(at = at(moment), state = state, applicationName = app?.first ?: "", executableName = app?.second ?: ""),
            )
            moment += step
        }
        return closed
    }

    @Test
    fun `steady state closes nothing`() {
        val builder = SessionBuilder()
        assertEquals(emptyList<ClosedSession>(), builder.observe(sample(0)))
        assertEquals(emptyList<ClosedSession>(), builder.observe(sample(2)))
        assertEquals(emptyList<ClosedSession>(), builder.observe(sample(4)))
        assertEquals(
            mapOf("state" to SessionBuilder.TYPE_ACTIVE, "application" to SessionBuilder.TYPE_APPLICATION),
            builder.openTracks,
        )
    }

    @Test
    fun `app switch closes the application session only`() {
        val builder = SessionBuilder()
        assertEquals(emptyList<ClosedSession>(), feed(builder, 0, 120))
        val closed = builder.observe(sample(122, app = chrome))

        assertEquals(1, closed.size)
        val session = closed[0]
        assertEquals(SessionBuilder.TYPE_APPLICATION, session.activityType)
        assertEquals("Visual Studio Code", session.applicationName)
        assertEquals("com.vscode", session.executableName)
        assertEquals(122L, session.durationSeconds)
        // The state track is unaffected: the user was active throughout.
        assertEquals(SessionBuilder.TYPE_ACTIVE, builder.openTracks["state"])
    }

    @Test
    fun `going idle closes both tracks and starts an idle session`() {
        val builder = SessionBuilder()
        feed(builder, 0, 120)
        val closed = byType(builder.observe(sample(122, state = Sample.STATE_IDLE)))

        assertEquals(122L, closed[SessionBuilder.TYPE_ACTIVE]!!.durationSeconds)
        assertEquals(122L, closed[SessionBuilder.TYPE_APPLICATION]!!.durationSeconds)
        // A phone left unattended must not report time as "using Visual Studio Code".
        assertEquals(mapOf("state" to SessionBuilder.TYPE_IDLE), builder.openTracks)
    }

    @Test
    fun `returning from idle reopens the application track`() {
        val builder = SessionBuilder()
        feed(builder, 0, 120)
        feed(builder, 122, 300, state = Sample.STATE_IDLE)
        val closed = builder.observe(sample(302))

        assertEquals(SessionBuilder.TYPE_IDLE, closed[0].activityType)
        assertEquals(180L, closed[0].durationSeconds)
        assertEquals(
            mapOf("state" to SessionBuilder.TYPE_ACTIVE, "application" to SessionBuilder.TYPE_APPLICATION),
            builder.openTracks,
        )
    }

    @Test
    fun `long use is split at the cap`() {
        val builder = SessionBuilder(maxSessionSeconds = 60)
        val closed = feed(builder, 0, 60)

        assertEquals(2, closed.size) // both tracks hit the cap together
        val application = byType(closed)[SessionBuilder.TYPE_APPLICATION]!!
        assertEquals(60L, application.durationSeconds)
        // Reopened immediately with the same values, so a crash costs a quarter of an
        // hour rather than the whole session.
        assertEquals(SessionBuilder.TYPE_APPLICATION, builder.openTracks["application"])
        assertEquals(emptyList<ClosedSession>(), feed(builder, 62, 118))
    }

    @Test
    fun `split sessions get distinct event ids`() {
        val builder = SessionBuilder(maxSessionSeconds = 30)
        val first = feed(builder, 0, 30)
        val second = feed(builder, 32, 60)

        val ids = (first + second).map { it.clientEventId }.toSet()
        // Reusing an id would make the server treat the second interval as a replay
        // of the first and silently drop it.
        assertEquals(first.size + second.size, ids.size)
    }

    @Test
    fun `a gap in samples closes at the last sample not the resumption`() {
        val builder = SessionBuilder()
        feed(builder, 0, 60)

        // The phone was locked and untouched for twenty minutes: nothing was observed.
        val closed = byType(builder.observe(sample(60 + 20 * 60)))

        assertEquals(60L, closed[SessionBuilder.TYPE_ACTIVE]!!.durationSeconds)
        assertEquals(60L, closed[SessionBuilder.TYPE_APPLICATION]!!.durationSeconds)
        assertEquals(at(60).toString(), closed[SessionBuilder.TYPE_ACTIVE]!!.endTime)
        assertEquals(SessionBuilder.TYPE_ACTIVE, builder.openTracks["state"])
    }

    @Test
    fun `a gap just inside the threshold is not a gap`() {
        val builder = SessionBuilder()
        builder.observe(sample(0))
        // A slow tick is not a gap.
        assertEquals(emptyList<ClosedSession>(), builder.observe(sample(SessionBuilder.MAX_SAMPLE_GAP_SECONDS)))
    }

    @Test
    fun `a clock that steps backwards does not produce negative time`() {
        val builder = SessionBuilder()
        feed(builder, 540, 600)
        val closed = builder.observe(sample(0))

        assertTrue(closed.all { it.durationSeconds >= 0 })
        assertEquals(SessionBuilder.TYPE_ACTIVE, builder.openTracks["state"])
    }

    @Test
    fun `no foreground app closes the application track only`() {
        val builder = SessionBuilder()
        feed(builder, 0, 28)
        // The lock screen and home launcher have no app to attribute time to.
        val closed = builder.observe(sample(30, app = null))

        assertEquals(listOf(SessionBuilder.TYPE_APPLICATION), closed.map { it.activityType })
        assertEquals(mapOf("state" to SessionBuilder.TYPE_ACTIVE), builder.openTracks)
    }

    @Test
    fun `sub-second sessions are dropped`() {
        val builder = SessionBuilder()
        builder.observe(sample(0))
        // An artefact of sampling, not a fact about the day.
        assertEquals(emptyList<ClosedSession>(), builder.observe(Sample(at = at(0), applicationName = chrome.first, executableName = chrome.second)))
    }

    @Test
    fun `flush closes everything and resets`() {
        val builder = SessionBuilder()
        feed(builder, 0, 60)
        val closed = builder.flush(at(120))

        assertEquals(2, closed.size)
        assertEquals(emptyMap<String, String>(), builder.openTracks)
        // After a flush the next sample starts fresh rather than being treated as a gap.
        assertEquals(emptyList<ClosedSession>(), builder.observe(sample(3600)))
    }
}
