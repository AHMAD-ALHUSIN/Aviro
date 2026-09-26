[app]

# (str) Title of your application
title = YTDownloader

# (str) Package name
package.name = ytdownloader

# (str) Package domain (needed for android/ios packaging)
package.domain = org.myapps

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas

# (str) Application versioning
version = 0.1

# (list) Application requirements
# قمنا بإزالة hostpython وتقييد الإصدارات لمنع فشل البناء
requirements = python3, kivy==2.2.1, pillow, yt-dlp, certifi, idna, urllib3, requests, ffpyplayer

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (list) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
# الأذونات المطلوبة لتحميل الملفات وتخزينها
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK / AAB will support.
android.minapi = 21

# (str) Android architecture to build for (arm64-v8a is required by Google Play)
android.archs = arm64-v8a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
# جعلته 2 ليظهر لك تفاصيل الأخطاء بوضوح في حال فشل GitHub Actions مستقبلاً
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
