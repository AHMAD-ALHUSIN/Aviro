import os
import json
import time
import copy
import threading
import concurrent.futures

from jnius import autoclass, detach
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

# استخدام شهادات certifi إن وُجدت بدل تعطيل التحقق من الشهادات
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
except Exception:
    pass

HOST = '127.0.0.1'
SERVICE_PORT = 3001
APP_PORT = 3002
IDLE_TIMEOUT = 60

# نهاية شريط التحميل عندما يلزم دمج (الباقي للدمج)
DOWNLOAD_END = 92.0
MERGE_END = 99.0

# اجعلها True فقط إذا ظهرت لك أخطاء SSL على جهاز معين
ALLOW_INSECURE_SSL = False

# استخراج معلومات الفيديو مرة واحدة وإعادة استخدامها للصوت والفيديو (يوفر عدة ثوانٍ)
REUSE_INFO = True

# أقل مساحة حرة (بايت) لاستخدام الذاكرة الداخلية للملفات المؤقتة
MIN_FREE_INTERNAL = 1024 * 1024 * 1024

PythonService = autoclass('org.kivy.android.PythonService')
Environment = autoclass('android.os.Environment')
MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
service = PythonService.mService

try:
    MediaMerger = autoclass('org.myapp.MediaMerger')
    MERGER_ERROR = None
except Exception as e:
    MediaMerger = None
    MERGER_ERROR = str(e)

client = OSCClient(HOST, APP_PORT, encoding='utf8')
osc_lock = threading.Lock()   # حماية إرسال OSC من الخيوط المتوازية
job_lock = threading.Lock()   # منع بدء مهمتين في نفس الوقت

state = {
    'busy': False,
    'user_cancel': False,   # إلغاء من المستخدم
    'abort': False,         # إيقاف داخلي (فشل أحد التحميلين)
    'percent': 0.0,
    'text': '',
    'last_activity': time.time(),
    'stop_at': 0,
    'merger': None,
}


class JobCancelled(Exception):
    pass


class YTDLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def write(self, msg): pass


# ------------------------------------------------------------------ helpers
def get_ytdlp():
    import yt_dlp
    return yt_dlp


def safe_detach():
    try:
        detach()
    except Exception:
        pass


def send(path, *args):
    try:
        with osc_lock:
            client.send_message(path, list(args))
    except Exception as e:
        print('OSC send failed:', e)


def report(percent, text):
    state['percent'] = float(percent)
    state['text'] = text
    send(b'/progress', float(percent), text)


def is_cancelled():
    return state['user_cancel'] or state['abort']


def is_cancel_exc(e):
    return (
        isinstance(e, JobCancelled)
        or 'DownloadCancelled' in type(e).__name__
        or 'DownloadCancelled' in str(e)
    )


def fmt_speed(bps):
    if not bps:
        return ''
    for unit in ('B/s', 'KB/s', 'MB/s'):
        if bps < 1024:
            return f'{bps:.0f} {unit}'
        bps /= 1024
    return f'{bps:.1f} GB/s'


def get_save_dir():
    try:
        d = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if d is not None:
            return d.getAbsolutePath()
    except Exception:
        pass
    return '/storage/emulated/0/Download'


def free_bytes(path):
    try:
        st = os.statvfs(path)
        return st.f_bavail * st.f_frsize
    except Exception:
        return 0


def cache_dirs():
    dirs = []
    try:
        d = service.getCacheDir()
        if d is not None:
            dirs.append(d.getAbsolutePath())   # داخلي (أسرع غالباً)
    except Exception:
        pass
    try:
        d = service.getExternalCacheDir()
        if d is not None:
            dirs.append(d.getAbsolutePath())
    except Exception:
        pass
    return dirs


def get_temp_dir():
    """يفضّل الذاكرة الداخلية (I/O أسرع) إذا كانت المساحة كافية."""
    dirs = cache_dirs()
    if not dirs:
        return '/data/local/tmp'
    for d in dirs:
        if free_bytes(d) >= MIN_FREE_INTERNAL:
            return d
    return max(dirs, key=free_bytes)


def cleanup_stale(max_age=3600):
    """حذف الملفات المؤقتة اليتيمة من تشغيلات سابقة."""
    now = time.time()
    for d in cache_dirs():
        try:
            for f in os.listdir(d):
                if f.endswith(('.tmp.mp4', '.tmp.m4a', '.part')):
                    p = os.path.join(d, f)
                    try:
                        if now - os.path.getmtime(p) > max_age:
                            os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass


def clean_title(raw):
    title = ''.join(c for c in (raw or '') if c.isalnum() or c in (' ', '_', '-')).strip()
    title = title[:100].strip()
    # حد اسم الملف 255 بايت (العربية = 2 بايت/حرف)
    while len(title.encode('utf-8')) > 200 and title:
        title = title[:-1]
    return title.strip() or 'Video'


def unique_path(folder, title, ext):
    path = os.path.join(folder, f'{title}.{ext}')
    n = 1
    while os.path.exists(path) or os.path.exists(path + '.part'):
        path = os.path.join(folder, f'{title} ({n}).{ext}')
        n += 1
    return path


def remove_quiet(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def scan_file(path):
    try:
        MediaScannerConnection.scanFile(service, [path], None, None)
    except Exception:
        pass


# ------------------------------------------------------------------ progress
class ProgressTracker:
    """يجمع تقدم عدة مسارات تحميل بالوزن الفعلي (بالبايت) بدل نسب ثابتة."""

    def __init__(self, names, label, scale):
        self.lock = threading.Lock()
        self.s = {n: {'frac': 0.0, 'w': 0, 'speed': 0.0, 'seen': False} for n in names}
        self.label = label
        self.scale = scale
        self.best = 0.0
        self.last_emit = 0.0
        self.last_pct = -1

    def update(self, name, frac, weight, speed, force=False):
        with self.lock:
            st = self.s[name]
            st['seen'] = True
            st['frac'] = frac
            if weight:
                st['w'] = weight
            st['speed'] = speed or 0.0

            seen = [x for x in self.s.values() if x['seen']]
            known = [x['w'] for x in seen if x['w'] > 0]
            avg = (sum(known) / len(known)) if known else 1.0
            total_w = 0.0
            acc = 0.0
            for x in seen:
                w = x['w'] or avg
                total_w += w
                acc += x['frac'] * w
            overall = acc / total_w if total_w else 0.0
            self.best = max(self.best, overall)   # لا يرجع الشريط للخلف أبداً

            now = time.time()
            pct = int(self.best * 100)
            due = (pct > self.last_pct and now - self.last_emit >= 0.15) or (now - self.last_emit >= 0.5)
            if force or due:
                self.last_pct = pct
                self.last_emit = now
                speed_total = sum(x['speed'] for x in seen)
                text = f'{self.label} {pct}%'
                sp = fmt_speed(speed_total)
                if sp:
                    text += f' | {sp}'
                report(self.best * self.scale, text)


def make_hook(tracker, name):
    yt_dlp = get_ytdlp()

    def hook(d):
        if is_cancelled():
            raise yt_dlp.utils.DownloadCancelled()

        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            if total:
                frac = min(done / total, 1.0)
            elif d.get('fragment_count'):
                frac = min((d.get('fragment_index') or 0) / d['fragment_count'], 1.0)
            else:
                frac = 0.0
            tracker.update(name, frac, total, d.get('speed'))
        elif status == 'finished':
            tracker.update(name, 1.0, d.get('total_bytes') or d.get('downloaded_bytes') or 0, 0, force=True)

    return hook


# ------------------------------------------------------------------ yt-dlp
def base_opts(fmt, out_path=None, hook=None):
    opts = {
        'format': fmt,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
        'logger': YTDLogger(),
        'nocheckcertificate': ALLOW_INSECURE_SSL,
        'retries': 10,
        'fragment_retries': 10,
        'concurrent_fragment_downloads': 4,
        'http_chunk_size': 10485760,
        'buffersize': 65536,
        'socket_timeout': 30,
        'updatetime': False,
    }
    if out_path:
        opts['outtmpl'] = out_path
    if hook:
        opts['progress_hooks'] = [hook]
    return opts


def fetch_info(url, fmt):
    """استخراج المعلومات مرة واحدة فقط. عند الفشل نعود للطريقة العادية."""
    if not REUSE_INFO:
        return None
    yt_dlp = get_ytdlp()
    try:
        with yt_dlp.YoutubeDL(base_opts(fmt)) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or info.get('_type') not in (None, 'video'):
                return None
            return yt_dlp.YoutubeDL.sanitize_info(info, remove_private_keys=True)
    except Exception as e:
        if is_cancel_exc(e):
            raise
        return None


def download_stream(info, url, fmt, out_path, hook):
    yt_dlp = get_ytdlp()
    with yt_dlp.YoutubeDL(base_opts(fmt, out_path, hook)) as ydl:
        if info is not None:
            ydl.process_ie_result(copy.deepcopy(info), download=True)
        else:
            ydl.download([url])


def download_worker(*args):
    try:
        download_stream(*args)
    finally:
        safe_detach()   # فصل خيط التحميل عن JVM


# ------------------------------------------------------------------ merge
def run_merge(video_tmp, audio_tmp, final_path):
    merger = MediaMerger()
    state['merger'] = merger
    stop = threading.Event()

    def poll():
        try:
            while not stop.wait(0.3):
                try:
                    p = int(merger.getProgress())
                except Exception:
                    continue
                report(DOWNLOAD_END + (MERGE_END - DOWNLOAD_END) * p / 100.0, f'Merging {p}%')
        finally:
            safe_detach()

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        report(DOWNLOAD_END, 'Merging 0%')
        return str(merger.mergeBlocking(service, video_tmp, audio_tmp, final_path))
    finally:
        stop.set()
        t.join(1.0)
        state['merger'] = None


# ------------------------------------------------------------------ main job
def run_job(job):
    final_path = None
    tmp_files = []
    success = False

    try:
        url = job['url']
        video_id = job.get('video_id')
        audio_id = job.get('audio_id')
        title = clean_title(job.get('title'))

        if video_id is None and audio_id is None:
            raise RuntimeError('No format selected.')

        save_dir = get_save_dir()
        os.makedirs(save_dir, exist_ok=True)
        report(0, 'Starting...')

        need_merge = video_id is not None and audio_id is not None
        if need_merge and MediaMerger is None:
            raise RuntimeError(f'MediaMerger not loaded: {MERGER_ERROR}')

        # استخراج المعلومات مرة واحدة
        report(0, 'Preparing...')
        info = fetch_info(url, video_id or audio_id)
        if state['user_cancel']:
            raise JobCancelled()

        if not need_merge:
            # صوت فقط أو فيديو جاهز (مدمج)
            audio_only = video_id is None
            fmt = audio_id if audio_only else video_id
            final_path = unique_path(save_dir, title, 'm4a' if audio_only else 'mp4')
            label = 'Downloading audio' if audio_only else 'Downloading'
            tracker = ProgressTracker(('main',), label, 100.0)
            download_stream(info, url, fmt, final_path, make_hook(tracker, 'main'))
        else:
            final_path = unique_path(save_dir, title, 'mp4')
            stamp = int(time.time() * 1000)
            temp_dir = get_temp_dir()
            video_tmp = os.path.join(temp_dir, f'{stamp}_video.tmp.mp4')
            audio_tmp = os.path.join(temp_dir, f'{stamp}_audio.tmp.m4a')
            tmp_files = [video_tmp, audio_tmp, video_tmp + '.part', audio_tmp + '.part']

            tracker = ProgressTracker(('video', 'audio'), 'Downloading', DOWNLOAD_END)
            real_err = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(download_worker, info, url, video_id, video_tmp, make_hook(tracker, 'video')),
                    executor.submit(download_worker, info, url, audio_id, audio_tmp, make_hook(tracker, 'audio')),
                ]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        f.result()
                    except Exception as e:
                        if not is_cancel_exc(e) and real_err is None:
                            real_err = e
                            state['abort'] = True   # أوقف التحميل الآخر فوراً

            if real_err is not None:
                raise real_err
            if state['user_cancel']:
                raise JobCancelled()

            result = run_merge(video_tmp, audio_tmp, final_path)
            if result == 'CANCELLED':
                raise JobCancelled()
            if result != 'SUCCESS':
                raise RuntimeError(f'Merge Error: {result}')

        if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
            raise RuntimeError('Output file is missing or empty.')

        scan_file(final_path)
        success = True
        report(100, 'Done')
        send(b'/done', final_path)

    except Exception as e:
        if state['user_cancel'] or is_cancel_exc(e):
            send(b'/cancelled', 1)
        else:
            send(b'/error', str(e) or type(e).__name__)

    finally:
        remove_quiet(*tmp_files)
        if not success and final_path:
            remove_quiet(final_path, final_path + '.part')
        state['busy'] = False
        state['user_cancel'] = False
        state['abort'] = False
        state['merger'] = None
        state['last_activity'] = time.time()
        state['stop_at'] = time.time() + 2
        safe_detach()


# ------------------------------------------------------------------ OSC handlers
def on_download(payload):
    state['last_activity'] = time.time()
    try:
        job = json.loads(payload)
    except Exception as e:
        send(b'/error', f'Bad job data: {e}')
        return

    with job_lock:
        if state['busy']:
            send(b'/error', 'A download is already running.')
            return
        state['busy'] = True
        state['user_cancel'] = False
        state['abort'] = False
        state['percent'] = 0.0
        state['text'] = ''
        state['stop_at'] = 0

    threading.Thread(target=run_job, args=(job,), daemon=True).start()


def on_cancel(*_):
    if not state['busy']:
        return
    state['user_cancel'] = True
    merger = state.get('merger')
    if merger is not None:
        try:
            merger.cancel()
        except Exception:
            pass


def on_sync(*_):
    state['last_activity'] = time.time()
    send(b'/ready', 1)
    send(b'/state', 1 if state['busy'] else 0, float(state['percent']), state['text'])


def stop_service():
    try:
        service.stopSelf()
    except Exception as e:
        print('stopSelf failed:', e)


# ------------------------------------------------------------------ start
cleanup_stale()

server = OSCThreadServer(encoding='utf8')
server.listen(HOST, port=SERVICE_PORT, default=True)
server.bind(b'/download', on_download)
server.bind(b'/cancel', on_cancel)
server.bind(b'/sync', on_sync)

send(b'/ready', 1)

while True:
    time.sleep(0.5)
    now = time.time()
    if state['stop_at'] and now >= state['stop_at'] and not state['busy']:
        stop_service()
        state['stop_at'] = 0
    elif not state['busy'] and now - state['last_activity'] > IDLE_TIMEOUT:
        stop_service()
        state['last_activity'] = now
