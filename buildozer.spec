[app]
title = Gold Signals
package.name = goldsignals
package.domain = org.example
source.dir = .
source.include_exts = py
source.exclude_dirs = .github, bin
version = 1.0
requirements = python3,kivy==2.3.0,openssl,certifi
orientation = portrait
fullscreen = 0
android.permissions = INTERNET, WAKE_LOCK
android.wakelock = True
android.api = 33
android.minapi = 21
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0
