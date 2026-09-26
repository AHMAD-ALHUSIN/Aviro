[app]

title = YTDownloader
package.name = ytdownloader
package.domain = org.myapps
source.dir = .

source.include_exts = py, png, jpg, kv, atlas, so
source.include_patterns = ffmpeg, *.so

version = 0.1

requirements = python3, kivy==2.2.1, pillow, yt-dlp, certifi, idna, urllib3, requests

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

[buildozer]
log_level = 2
warn_on_root = 1
