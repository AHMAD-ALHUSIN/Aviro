"""
تنزيل APK التحديث وتثبيته من داخل التطبيق (أندرويد فقط).

الطريقة:
  - التنزيل عبر DownloadManager الخاص بالنظام (يعمل بالخلفية، ويعرض إشعاراً،
    ولا يحتاج إذن تخزين ولا FileProvider).
  - بعد اكتمال التنزيل يُفتح مثبّت النظام، ويضغط المستخدم "تحديث/Install" فقط.
  - يحتاج إذن REQUEST_INSTALL_PACKAGES في buildozer.spec، ويوافق المستخدم مرة واحدة
    على "التثبيت من هذا التطبيق" (تفتح الدالة request_install_permission شاشة الإعداد).

كل الدوال تُستدعى من الخيط الرئيسي (Kivy) فقط.
"""

from kivy.clock import Clock
from jnius import autoclass

APK_MIME = 'application/vnd.android.package-archive'
FILE_NAME = 'Aviro-update.apk'


def _activity():
    return autoclass('org.kivy.android.PythonActivity').mActivity


def can_install():
    """هل سمح المستخدم لهذا التطبيق بتثبيت التطبيقات؟ (أندرويد 8+)."""
    try:
        sdk = autoclass('android.os.Build$VERSION').SDK_INT
        if sdk >= 26:
            return bool(_activity().getPackageManager().canRequestPackageInstalls())
    except Exception:
        pass
    return True


def request_install_permission():
    """يفتح شاشة إعداد 'التثبيت من هذا المصدر' الخاصة بتطبيقنا."""
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

    # -------------------------------------------------------------- download
    def start(self, url, file_name=FILE_NAME):
        Context = autoclass('android.content.Context')
        Environment = autoclass('android.os.Environment')
        Uri = autoclass('android.net.Uri')
        Request = autoclass('android.app.DownloadManager$Request')
        act = _activity()

        # حذف أي APK قديم من تنزيلات سابقة حتى لا تتراكم الملفات
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
        self._event = Clock.schedule_interval(self._poll, 1)

    def _poll(self, dt):
        try:
            DM = autoclass('android.app.DownloadManager')
            Query = autoclass('android.app.DownloadManager$Query')
            cursor = self.dm.query(Query().setFilterById([self.download_id]))
            try:
                if not cursor.moveToFirst():
                    return self._fail('Download was removed.')
                status = cursor.getInt(cursor.getColumnIndex(DM.COLUMN_STATUS))
                done = cursor.getLong(cursor.getColumnIndex(DM.COLUMN_BYTES_DOWNLOADED_SO_FAR))
                total = cursor.getLong(cursor.getColumnIndex(DM.COLUMN_TOTAL_SIZE_BYTES))
            finally:
                cursor.close()

            if status == DM.STATUS_SUCCESSFUL:
                self._stop_timer()
                self.apk_uri = self.dm.getUriForDownloadedFile(self.download_id)
                self.on_ready()
                self.install()
            elif status == DM.STATUS_FAILED:
                self._fail('Download failed.')
            elif status == DM.STATUS_PAUSED:
                self.on_progress(0.0, 'Waiting for network...')
            else:
                pct = (done * 100.0 / total) if total and total > 0 else 0.0
                self.on_progress(pct, f'Downloading {int(pct)}%')
        except Exception as e:
            self._fail(str(e) or 'Download error.')

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
            self._fail(str(e) or 'Could not open the installer.')

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
                self.dm.remove([self.download_id])
        except Exception:
            pass
