package com.officemanagement.tracking.di

import android.content.Context
import com.officemanagement.tracking.storage.TrackingDatabase
import com.officemanagement.tracking.storage.TrackingSessionDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object TrackingModule {

    @Provides
    @Singleton
    fun provideTrackingDatabase(@ApplicationContext context: Context): TrackingDatabase =
        TrackingDatabase.build(context)

    @Provides
    fun provideTrackingSessionDao(database: TrackingDatabase): TrackingSessionDao = database.sessionDao()
}
