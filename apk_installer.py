from kivy.clock import Clock
from jnius import autoclass, jarray

APK_MIME = 'application/vnd.android.package-archive'
FILE_NAME = 'Aviro-update.apk'
POLL_INTERVAL = 1.0


def _activity():
    return autoclass('org.kivy.android.PythonActivity').mActivity


def can_install():
    """هل سمح المستخدم لهذا التطبيق بتثبيت التطبيقات؟ (أندرويد 8+)."""
    try:
        if autoclass('android.os.Build$VERSION').SDK_INT >= 26:
            return bool(_activity().getPackageManager().canRequestPackageInstalls())
    except Exception:
        pass
    return True


def request_install_permission():
    """يفتح شاشة 'التثبيت من هذا المصدر' الخاصة بتطبيقنا."""
    Settings = autoclass('android.provider.Settings')
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    act = _activity()
    intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse('package:' + act.getPackageName()))
    act.startActivity(intent)


class ApkUpdater:
    """
    on_progress(percent: float, text: str)  أثناء التنزيل
    on_ready()                              عند اكتمال التنزيل
    on_error(message: str)                  عند أي فشل
    on_need_permission()                    (اختياري) عند غياب إذن التثبيت
    """

    def __init__(self, on_progress, on_ready, on_error, on_need_permission=None):
        self.on_progress = on_progress
        self.on_ready = on_ready
        self.on_error = on_error
        self.on_need_permission = on_need_permission
        self.dm = None
        self.download_id = None
        self.apk_uri = None
        self._event = None
        self._expected_size = None

        # نخزّن الكلاسات مرة واحدة بدل استدعاء autoclass كل ثانية
        self._DM = autoclass('android.app.DownloadManager')
        self._Query = autoclass('android.app.DownloadManager$Query')

    # -------------------------------------------------------------- download
    def start(self, url, file_name=FILE_NAME, expected_size=None):
        if self._event is not None:          # تنزيل جارٍ بالفعل
            return
        self._expected_size = expected_size
        try:
            Context = autoclass('android.content.Context')
            Environment = autoclass('android.os.Environment')
            Uri = autoclass('android.net.Uri')
            Request = autoclass('android.app.DownloadManager$Request')
            act = _activity()

            self._clean_old_apks(act, Environment)

            self.dm = act.getSystemService(Context.DOWNLOAD_SERVICE)
            req = Request(Uri.parse(url))
            req.setTitle('Aviro update')
            req.setMimeType(APK_MIME)
            req.setNotificationVisibility(
                Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            req.setDestinationInExternalFilesDir(
                act, Environment.DIRECTORY_DOWNLOADS, file_name)
            self.download_id = self.dm.enqueue(req)
            self._event = Clock.schedule_interval(self._poll, POLL_INTERVAL)
        except Exception as e:
            self._fail(str(e) or 'تعذّر بدء التنزيل.')

    @staticmethod
    def _clean_old_apks(act, Environment):
        try:
            folder = act.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            files = folder.listFiles() if folder is not None else None
            for f in (files or []):
                if str(f.getName()).endswith('.apk'):
                    f.delete()
        except Exception:
            pass

    def _poll(self, dt):
        DM = self._DM
        try:
            ids = jarray('j')([self.download_id])
            cursor = self.dm.query(self._Query().setFilterById(ids))
            try:
                if not cursor.moveToFirst():
                    return self._fail('تمت إزالة التنزيل.')
                status = cursor.getInt(cursor.getColumnIndex(DM.COLUMN_STATUS))
                done = cursor.getLong(
                    cursor.getColumnIndex(DM.COLUMN_BYTES_DOWNLOADED_SO_FAR))
                total = cursor.getLong(
                    cursor.getColumnIndex(DM.COLUMN_TOTAL_SIZE_BYTES))
            finally:
                cursor.close()
        except Exception as e:
            return self._fail(str(e) or 'خطأ أثناء التنزيل.')

        if status == DM.STATUS_SUCCESSFUL:
            self._stop_timer()
            self._on_downloaded(total)
        elif status == DM.STATUS_FAILED:
            self._fail('فشل التنزيل.')
        elif status == DM.STATUS_PAUSED:
            self.on_progress(0.0, 'بانتظار الشبكة...')
        elif status == DM.STATUS_PENDING:
            self.on_progress(0.0, 'في الانتظار...')
        else:
            pct = (done * 100.0 / total) if total and total > 0 else 0.0
            self.on_progress(pct, f'جارٍ التنزيل {int(pct)}%')

    def _on_downloaded(self, total):
        # تحقق بسيط من سلامة الملف
        if self._expected_size and total != self._expected_size:
            return self._fail('حجم الملف غير مطابق، حاول مجدداً.')
        try:
            self.apk_uri = self.dm.getUriForDownloadedFile(self.download_id)
        except Exception as e:
            return self._fail(str(e) or 'تعذّر الوصول إلى الملف.')
        if self.apk_uri is None:
            return self._fail('الملف غير متاح.')

        # on_ready معزولة حتى لا يؤدي خطؤها إلى إلغاء التثبيت
        try:
            self.on_ready()
        except Exception:
            pass
        self.install()

    # -------------------------------------------------------------- install
    def install(self):
        """يفتح مثبّت النظام (يجب أن يكون التطبيق في الواجهة الأمامية)."""
        if self.apk_uri is None:
            return self._fail('الملف غير جاهز.')
        if not can_install():
            if self.on_need_permission:
                self.on_need_permission()    # اعرض للمستخدم شرحاً ثم استدعِ request_install_permission()
            else:
                request_install_permission()
            return
        try:
            Intent = autoclass('android.content.Intent')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(self.apk_uri, APK_MIME)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION |
                            Intent.FLAG_ACTIVITY_NEW_TASK)
            _activity().startActivity(intent)
        except Exception as e:
            self._fail(str(e) or 'تعذّر فتح المثبّت.')

    # -------------------------------------------------------------- internals
    def _stop_timer(self):
        if self._event is not None:
            self._event.cancel()
            self._event = None

    def _fail(self, message):
        self._stop_timer()
        self.on_error(message)

    def cancel(self):
        self._stop_timer()
        try:
            if self.dm is not None and self.download_id is not None:
                self.dm.remove(jarray('j')([self.download_id]))
        except Exception:
            pass
