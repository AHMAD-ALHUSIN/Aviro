[app]

title = Aviro
package.name = ytdownloader
package.domain = org.myapp
source.dir = .

source.include_exts = py, png, jpg, kv, atlas

version = 0.2

# oscpy للتواصل بين التطبيق والخدمة
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.2.1,pillow,yt-dlp,certifi,idna,urllib3,requests,pyjnius,oscpy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, FOREGROUND_SERVICE, FOREGROUND_SERVICE_DATA_SYNC, POST_NOTIFICATIONS, WAKE_LOCK, READ_MEDIA_VIDEO, READ_MEDIA_AUDIO

android.api = 34
android.minapi = 21

android.accept_sdk_license = True
android.build_tools_version = 34.0.0

android.ndk = 25c
android.archs = arm64-v8a
android.allow_backup = True

# خدمة التنزيل (تعمل كـ Foreground Service)
services = downloader:service.py:foreground
android.foreground_service_types = dataSync

android.add_src = java
android.gradle_dependencies = androidx.media3:media3-transformer:1.3.0, androidx.media3:media3-common:1.3.0
android.enable_androidx = True

icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/icon_bg.png

presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #12141A

android.proguard_rules = proguard-rules.pro

[buildozer]
log_level = 2
warn_on_root = 1
