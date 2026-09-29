from kivy.clock import Clock
from jnius import autoclass

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
    on_ready()                              عند اكتمال التنزيل (ثم يُحاول التثبيت تلقائياً)
    on_error(message: str)                  عند أي فشل
    """

    def __init__(self, on_progress, on_ready, on_error):
        self.on_progress = on_progress
        self.on_ready = on_ready
        self.on_error = on_error
        self.dm = None
        self.download_id = None
        self.apk_uri = None
        self._event = None
        self._DM = autoclass('android.app.DownloadManager')
        self._Query = autoclass('android.app.DownloadManager$Query')

    # -------------------------------------------------------------- download
    def start(self, url, file_name=FILE_NAME):
        if self._event is not None:      # تنزيل جارٍ بالفعل
            return
        try:
            Context = autoclass('android.content.Context')
            Environment = autoclass('android.os.Environment')
            Uri = autoclass('android.net.Uri')
            Request = autoclass('android.app.DownloadManager$Request')
            act = _activity()

            # حذف أي APK قديم حتى لا تتراكم الملفات
            folder = act.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            if folder is not None:
                files = folder.listFiles()
                if files:
                    for f in files:
                        if str(f.getName()).endswith('.apk'):
                            f.delete()

            self.dm = act.getSystemService(Context.DOWNLOAD_SERVICE)
            req = Request(Uri.parse(url))
            req.setTitle('Aviro update')
            req.setMimeType(APK_MIME)
            req.setNotificationVisibility(Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            req.setDestinationInExternalFilesDir(act, Environment.DIRECTORY_DOWNLOADS, file_name)
            self.download_id = self.dm.enqueue(req)
            self._event = Clock.schedule_interval(self._poll, POLL_INTERVAL)
        except Exception as e:
            self._fail(f'Start failed: {type(e).__name__}: {e}')

    def _poll(self, dt):
        DM = self._DM
        status = None
        done = total = 0
        try:
            # نقرأ كل تنزيلات تطبيقنا ونختار تنزيلنا بالرقم (بدون مصفوفات جافا)
            cursor = self.dm.query(self._Query())
            try:
                id_col = cursor.getColumnIndex(DM.COLUMN_ID)
                while cursor.moveToNext():
                    if cursor.getLong(id_col) == self.download_id:
                        status = cursor.getInt(cursor.getColumnIndex(DM.COLUMN_STATUS))
                        done = cursor.getLong(cursor.getColumnIndex(DM.COLUMN_BYTES_DOWNLOADED_SO_FAR))
                        total = cursor.getLong(cursor.getColumnIndex(DM.COLUMN_TOTAL_SIZE_BYTES))
                        break
            finally:
                cursor.close()
        except Exception as e:
            return self._fail(f'Query failed: {type(e).__name__}: {e}')

        if status is None:
            return self._fail('Download was removed.')

        if status == DM.STATUS_SUCCESSFUL:
            self._stop_timer()
            self._on_downloaded()
        elif status == DM.STATUS_FAILED:
            self._fail('Download failed.')
        elif status == DM.STATUS_PAUSED:
            self.on_progress(0.0, 'Waiting for network...')
        elif status == DM.STATUS_PENDING:
            self.on_progress(0.0, 'Waiting to start...')
        else:
            pct = (done * 100.0 / total) if total and total > 0 else 0.0
            self.on_progress(pct, f'Downloading {int(pct)}%')

    def _on_downloaded(self):
        try:
            self.apk_uri = self.dm.getUriForDownloadedFile(self.download_id)
        except Exception as e:
            return self._fail(f'File access failed: {type(e).__name__}: {e}')
        if self.apk_uri is None:
            return self._fail('Downloaded file is not available.')
        try:
            self.on_ready()
        except Exception:
            pass                      # خطأ في الواجهة لا يجب أن يمنع التثبيت
        self.install()

    # -------------------------------------------------------------- install
    def install(self):
        """يفتح مثبّت النظام (يجب أن يكون التطبيق في الواجهة الأمامية)."""
        try:
            if self.apk_uri is None:
                raise RuntimeError('APK is not ready.')
            Intent = autoclass('android.content.Intent')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(self.apk_uri, APK_MIME)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
            _activity().startActivity(intent)
        except Exception as e:
            self._fail(f'Installer failed: {type(e).__name__}: {e}')

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
                self.dm.remove(self.download_id)
        except Exception:
            pass
