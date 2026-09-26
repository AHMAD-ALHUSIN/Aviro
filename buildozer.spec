[app]
title = محمل الفيديوهات
package.name = ytdownloader
package.domain = org.ahmad

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

# Python 3.11 مثبّت صراحةً في كل مكان — هذا هو المفتاح
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.2.1,yt-dlp,certifi,idna,urllib3,requests

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True

p4a.remove_paths = Modules/grpmodule.c,Modules/spwdmodule.c

[buildozer]
log_level = 2
warn_on_root = 1
