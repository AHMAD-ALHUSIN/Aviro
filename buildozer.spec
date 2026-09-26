[app]

# (str) Title of your application
title = YTDownloader

# (str) Package name
package.name = ytdownloader

# (str) Package domain (needed for android/ios packaging)
package.domain = org.myapps

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas

# (list) Patterns to include (تضمين ملف ffmpeg التنفيذي بدون امتداد)
source.include_patterns = ffmpeg

# (str) Application versioning
version = 0.1

# (list) Application requirements
requirements = python3, kivy==2.2.1, pillow, yt-dlp, certifi, idna, urllib3, requests, ffpyplayer

# (list) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (int) Target Android API
android.api = 33

# (int) Minimum API supported
android.minapi = 21

# (str) Android architecture
android.archs = arm64-v8a

# (bool) enables Android auto backup feature
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
