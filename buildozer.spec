[app]

title = YTDownloader
package.name = ytdownloader
package.domain = org.myapps
source.dir = .

source.include_exts = py, png, jpg, kv, atlas, java
source.include_patterns = ffmpeg, *.so

version = 0.1

# تم إضافة pyjnius للاستدعاءات الخاصة بنظام الأندرويد
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.2.1,pillow,yt-dlp,certifi,idna,urllib3,requests,pyjnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

android.api = 34
android.minapi = 21

android.accept_sdk_license = True
android.build_tools_version = 34.0.0

android.ndk = 25c
android.archs = arm64-v8a
android.allow_backup = True

android.add_src = src/java
android.gradle_dependencies = androidx.media3:media3-transformer:1.3.0, androidx.media3:media3-common:1.3.0
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
