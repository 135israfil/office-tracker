package com.officemanagement.tracking.storage

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

/** The offline buffer for closed tracking sessions (§19 for phones) — a Room port of
 * desktop-agent/agent/storage/queue.py's SessionQueue. Every closed session is written
 * here *before* anything tries to upload it, and the `synced` flag is set only after the
 * server answers 2xx: the failure mode this rules out is "uploaded but lost", and the
 * failure mode it accepts — "uploaded twice" — is harmless because the server upserts on
 * `client_event_id`. */
@Entity(
    tableName = "tracking_sessions",
    indices = [Index(value = ["clientEventId"], unique = true), Index(value = ["synced", "id"])],
)
data class TrackingSessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val clientEventId: String,
    val activityType: String,
    val applicationName: String = "",
    val executableName: String = "",
    val websiteDomain: String = "",
    val startTime: String,
    val endTime: String,
    val createdAt: Long,
    val synced: Boolean = false,
    val syncedAt: Long? = null,
    val attempts: Int = 0,
)

data class TrackingQueueStats(val total: Int, val pending: Int, val maxAttempts: Int)

@Dao
interface TrackingSessionDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(session: TrackingSessionEntity): Long

    @Query("SELECT * FROM tracking_sessions WHERE synced = 0 ORDER BY id LIMIT :limit")
    suspend fun pending(limit: Int = 100): List<TrackingSessionEntity>

    @Query("SELECT COUNT(*) FROM tracking_sessions WHERE synced = 0")
    suspend fun pendingCount(): Int

    @Query("UPDATE tracking_sessions SET synced = 1, syncedAt = :at WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<Long>, at: Long)

    @Query("UPDATE tracking_sessions SET attempts = attempts + 1 WHERE id IN (:ids)")
    suspend fun recordAttempt(ids: List<Long>)

    @Query("DELETE FROM tracking_sessions WHERE id IN (:ids)")
    suspend fun discard(ids: List<Long>)

    @Query("DELETE FROM tracking_sessions WHERE synced = 1 AND syncedAt < :before")
    suspend fun purgeSyncedBefore(before: Long): Int

    @Query(
        "SELECT COUNT(*) AS total, " +
            "SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) AS pending, " +
            "COALESCE(MAX(attempts), 0) AS maxAttempts " +
            "FROM tracking_sessions",
    )
    suspend fun stats(): TrackingQueueStatsRow

    @Query("SELECT COUNT(*) FROM tracking_sessions")
    suspend fun totalCount(): Int
}

/** Room needs a concrete row shape for the aggregate query above; [TrackingQueueStats]
 * stays the clean public type callers see (see TrackingQueueRepository.stats()). */
data class TrackingQueueStatsRow(val total: Int, val pending: Int?, val maxAttempts: Int)

@Database(entities = [TrackingSessionEntity::class], version = 1, exportSchema = false)
abstract class TrackingDatabase : RoomDatabase() {
    abstract fun sessionDao(): TrackingSessionDao

    companion object {
        const val DATABASE_NAME = "tracking_queue.db"

        fun build(context: android.content.Context): TrackingDatabase =
            Room.databaseBuilder(context, TrackingDatabase::class.java, DATABASE_NAME).build()
    }
}
