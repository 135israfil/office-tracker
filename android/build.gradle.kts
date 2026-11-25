// Top-level build file: applies no plugins itself, just declares versions once for
// every module (currently just :app) to pick up — see gradle/libs.versions.toml for
// the actual version numbers.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.hilt.android) apply false
    alias(libs.plugins.ksp) apply false
}
