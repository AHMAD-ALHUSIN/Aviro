"""
تحديث yt-dlp أثناء عمل التطبيق بدون بناء APK جديد.

الفكرة:
  1. update_async() يسأل PyPI عن آخر إصدار، وإن وُجد أحدث من الموجود
     ينزّل الـ wheel ويتحقق من sha256 ثم يفك ضغطه في مجلد التطبيق الخاص.
  2. import_yt_dlp() يقدّم النسخة المحدَّثة على النسخة المضمّنة في الـ APK،
     وإن فشل استيرادها يحذفها ويرجع للنسخة المضمّنة تلقائياً.

يُستدعى import_yt_dlp() في main.py و service.py (عمليتان منفصلتان)،
ويُستدعى update_async() من main.py فقط، والتحديث يسري عند التشغيل التالي.
"""

import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import threading
import time
import urllib.request
import zipfile

PYPI_URL = 'https://pypi.org/pypi/yt-dlp/json'
ALLOWED_PREFIX = 'https://files.pythonhosted.org/'
CHECK_INTERVAL = 6 * 3600          # لا تفحص أكثر من مرة كل 6 ساعات
MAX_DOWNLOAD = 20 * 1024 * 1024    # حد أمان لحجم الملف
TIMEOUT = 20


def _root():
    base = os.environ.get('ANDROID_PRIVATE') or os.path.expanduser('~')
    return os.path.join(base, 'ytdlp_update')


ROOT = _root()
CURRENT = os.path.join(ROOT, 'current')     # يحتوي مجلد yt_dlp المحدَّث
META = os.path.join(ROOT, 'meta.json')


# ------------------------------------------------------------------ helpers
def _remove(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _vt(version):
    """يحوّل '2025.09.05' إلى (2025, 9, 5) للمقارنة."""
    return tuple(int(x) for x in re.findall(r'\d+', version or '')[:4])


def _read_version(pkg_dir):
    try:
        with open(os.path.join(pkg_dir, 'version.py'), encoding='utf-8') as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", f.read())
        return m.group(1) if m else None
    except OSError:
        return None


def _bundled_version():
    """نسخة yt-dlp المضمّنة في الـ APK (بدون استيرادها)."""
    for p in sys.path:
        if not p or os.path.abspath(p) == os.path.abspath(CURRENT):
            continue
        pkg = os.path.join(p, 'yt_dlp')
        if os.path.isdir(pkg):
            return _read_version(pkg)
    return None


def _effective_version():
    return _read_version(os.path.join(CURRENT, 'yt_dlp')) or _bundled_version()


def _load_meta():
    try:
        with open(META, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_meta(meta):
    try:
        tmp = META + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(meta, f)
        os.replace(tmp, META)
    except Exception:
        pass


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AviroUpdater/1.0'})
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context())


def _cleanup_leftovers(max_age=3600):
    """حذف بقايا تحديث فاشل أو قديم."""
    try:
        now = time.time()
        for name in os.listdir(ROOT):
            if name.startswith(('dl_', 'stage_', 'old_')):
                p = os.path.join(ROOT, name)
                try:
                    if now - os.path.getmtime(p) > max_age:
                        _remove(p)
                except Exception:
                    pass
    except Exception:
        pass


# ------------------------------------------------------------------ import
def prepare():
    """يجب استدعاؤه قبل أول import لـ yt_dlp: يقدّم النسخة المحدَّثة في sys.path."""
    if 'yt_dlp' in sys.modules:
        return
    pkg = os.path.join(CURRENT, 'yt_dlp')
    if not os.path.isdir(pkg):
        return

    updated = _read_version(pkg)
    bundled = _bundled_version()
    # إذا صار الـ APK نفسه أحدث (أو مساوياً) نتخلص من النسخة المحدَّثة
    if not updated or (bundled and _vt(bundled) >= _vt(updated)):
        _remove(CURRENT)
        return

    if CURRENT not in sys.path:
        sys.path.insert(0, CURRENT)


def import_yt_dlp():
    """يستورد yt_dlp، ويرجع للنسخة المضمّنة إذا فشلت النسخة المحدَّثة."""
    prepare()
    try:
        import yt_dlp
        return yt_dlp
    except Exception:
        while CURRENT in sys.path:
            sys.path.remove(CURRENT)
        for name in [m for m in sys.modules if m == 'yt_dlp' or m.startswith('yt_dlp.')]:
            del sys.modules[name]
        _remove(CURRENT)
        import yt_dlp
        return yt_dlp


# ------------------------------------------------------------------ update
def check_and_update(force=False):
    """يعيد رقم النسخة الجديدة إن تم تنزيلها، وإلا None."""
    os.makedirs(ROOT, exist_ok=True)
    _cleanup_leftovers()

    meta = _load_meta()
    if not force and time.time() - meta.get('last_check', 0) < CHECK_INTERVAL:
        return None

    with _open(PYPI_URL) as r:
        data = json.load(r)
    meta['last_check'] = time.time()
    _save_meta(meta)

    info = data.get('info', {})
    latest = info.get('version')
    if not latest:
        return None

    # تجاهل إن كانت النسخة تتطلب Python أحدث من المثبّت في التطبيق
    m = re.match(r'>=\s*3\.(\d+)', info.get('requires_python') or '')
    if m and int(m.group(1)) > sys.version_info.minor:
        return None

    current = _effective_version()
    if current and _vt(latest) <= _vt(current):
        return None

    wheel = next(
        (u for u in data.get('urls', [])
         if u.get('packagetype') == 'bdist_wheel' and u.get('filename', '').endswith('-none-any.whl')),
        None,
    )
    if not wheel:
        return None
    url = wheel['url']
    expected = (wheel.get('digests') or {}).get('sha256')
    if not url.startswith(ALLOWED_PREFIX) or not expected:
        return None

    stamp = int(time.time() * 1000)
    tmp_whl = os.path.join(ROOT, f'dl_{stamp}.whl')
    stage = os.path.join(ROOT, f'stage_{stamp}')
    old = os.path.join(ROOT, f'old_{stamp}')

    try:
        # 1) تنزيل مع التحقق من sha256
        h = hashlib.sha256()
        total = 0
        with _open(url) as r, open(tmp_whl, 'wb') as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError('download too large')
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != expected:
            raise ValueError('sha256 mismatch')

        # 2) فك الضغط إلى مجلد مؤقت (مجلد yt_dlp فقط)
        with zipfile.ZipFile(tmp_whl) as z:
            for name in z.namelist():
                if not name.startswith('yt_dlp/') or name.endswith('/'):
                    continue
                target = os.path.normpath(os.path.join(stage, name))
                if not target.startswith(stage + os.sep):
                    continue   # حماية من مسارات مشبوهة
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(name) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

        pkg = os.path.join(stage, 'yt_dlp')
        if not os.path.isfile(os.path.join(pkg, '__init__.py')) or _read_version(pkg) != latest:
            raise ValueError('invalid package')

        # 3) استبدال شبه فوري للنسخة الحالية
        if os.path.isdir(CURRENT):
            os.replace(CURRENT, old)
        os.replace(stage, CURRENT)
        _remove(old)
        return latest
    finally:
        _remove(tmp_whl)
        _remove(stage)


def update_async(callback=None, force=False):
    """يفحص ويحدّث في الخلفية دون إزعاج المستخدم عند أي فشل."""
    def worker():
        result = None
        try:
            result = check_and_update(force=force)
        except Exception as e:
            print('yt-dlp update failed:', e)
        if callback:
            try:
                callback(result)
            except Exception:
                pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t
