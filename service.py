import os
import json
import time
import threading
import concurrent.futures

from jnius import autoclass, detach
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

HOST = '127.0.0.1'
SERVICE_PORT = 3001
APP_PORT = 3002
IDLE_TIMEOUT = 60

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
osc_lock = threading.Lock()  # لحماية إرسال البيانات من الخيوط المتوازية

state = {
    'busy': False,
    'cancel': False,
    'percent': 0.0,
    'text': '',
    'last_activity': time.time(),
    'stop_at': 0,
    'video_frac': 0.0,  # لتتبع تقدم الفيديو بشكل منفصل
    'audio_frac': 0.0   # لتتبع تقدم الصوت بشكل منفصل
}

class YTDLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def write(self, msg): pass

# ------------------------------------------------------------------ helpers
def send(path, *args):
    try:
        # استخدام القفل لمنع تداخل الرسائل من خيوط التحميل المتوازية
        with osc_lock:
            client.send_message(path, list(args))
    except Exception as e:
        print('OSC send failed:', e)

def report(percent, text):
    state['percent'] = float(percent)
    state['text'] = text
    send(b'/progress', float(percent), text)

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

def get_cache_dir():
    try:
        d = service.getExternalCacheDir()
        if d is None:
            d = service.getCacheDir()
        return d.getAbsolutePath()
    except Exception:
        return '/data/local/tmp'

def clean_title(raw):
    title = ''.join(c for c in (raw or '') if c.isalnum() or c in (' ', '_', '-')).strip()
    return (title[:100].strip()) or 'Video'

def unique_path(folder, title, ext):
    path = os.path.join(folder, f'{title}.{ext}')
    n = 1
    while os.path.exists(path):
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

def make_hook(lo, hi, label):
    """تُستخدم للتحميل الفردي (صوت فقط أو فيديو فقط بدون دمج)"""
    import yt_dlp
    last_time = [0.0]
    last_percent = [0]

    def hook(d):
        if state['cancel']:
            raise yt_dlp.utils.DownloadCancelled()
        if d.get('status') != 'downloading':
            return
        
        now = time.time()
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        done = d.get('downloaded_bytes') or 0
        
        if total:
            frac = min(done / total, 1.0)
        elif d.get('fragment_count'):
            frac = min((d.get('fragment_index') or 0) / d['fragment_count'], 1.0)
        else:
            frac = 0.0

        current_percent = int(frac * 100)
        
        if current_percent > last_percent[0] or (now - last_time[0] > 0.5):
            last_percent[0] = current_percent
            last_time[0] = now
            speed = fmt_speed(d.get('speed'))
            text = f'{label} {current_percent}%'
            if speed:
                text += f' | {speed}'
            report(lo + (hi - lo) * frac, text)

    return hook

def make_parallel_hook(stream_type):
    """تُستخدم لدمج نسب التحميل للصوت والفيديو معاً أثناء التحميل المتوازي"""
    import yt_dlp
    last_time = [0.0]
    last_percent = [0]

    def hook(d):
        if state['cancel']:
            raise yt_dlp.utils.DownloadCancelled()
        if d.get('status') != 'downloading':
            return
        
        now = time.time()
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        done = d.get('downloaded_bytes') or 0
        
        if total:
            frac = min(done / total, 1.0)
        elif d.get('fragment_count'):
            frac = min((d.get('fragment_index') or 0) / d['fragment_count'], 1.0)
        else:
            frac = 0.0

        # تحديث نسبة هذا المسار فقط (صوت أو فيديو)
        state[f'{stream_type}_frac'] = frac

        # حساب النسبة الإجمالية: الفيديو يأخذ 75% من الشريط، والصوت 20% (المجموع 95%)
        v_frac = state.get('video_frac', 0.0)
        a_frac = state.get('audio_frac', 0.0)
        total_percent_float = (v_frac * 75.0) + (a_frac * 20.0)
        current_percent = int(total_percent_float)

        if current_percent > last_percent[0] or (now - last_time[0] > 0.5):
            last_percent[0] = current_percent
            last_time[0] = now
            speed = fmt_speed(d.get('speed'))
            
            # نعرض سرعة المسار الذي يرسل التحديث حالياً
            text = f'Downloading {current_percent}% | {speed}'
            report(total_percent_float, text)

    return hook

def download_stream(url, fmt, out_path, hook):
    import yt_dlp
    opts = {
        'format': fmt,
        'outtmpl': out_path,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'logger': YTDLogger(),
        'nocheckcertificate': True,
        'retries': 10,
        'fragment_retries': 10,
        'concurrent_fragment_downloads': 3,
        'http_chunk_size': 10485760,
        'socket_timeout': 30,
        'progress_hooks': [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

# ------------------------------------------------------------------ main job
def run_job(job):
    state['busy'] = True
    state['cancel'] = False
    final_path = None
    tmp_files = []
    success = False

    try:
        url = job['url']
        video_id = job.get('video_id')
        audio_id = job.get('audio_id')
        title = clean_title(job.get('title'))

        save_dir = get_save_dir()
        os.makedirs(save_dir, exist_ok=True)
        report(0, 'Starting...')

        if video_id is None and audio_id is not None:
            # تحميل صوت فقط
            final_path = unique_path(save_dir, title, 'm4a')
            download_stream(url, audio_id, final_path, make_hook(0, 100, 'Downloading audio'))

        elif audio_id is None:
            # تحميل فيديو مدمج جاهز (بدون مسار صوتي منفصل)
            final_path = unique_path(save_dir, title, 'mp4')
            download_stream(url, video_id, final_path, make_hook(0, 100, 'Downloading'))

        else:
            # تحميل الصوت والفيديو (متوازي Concurrent) ثم دمجهما
            if MediaMerger is None:
                raise RuntimeError(f'MediaMerger not loaded: {MERGER_ERROR}')

            final_path = unique_path(save_dir, title, 'mp4')
            stamp = int(time.time())
            cache_dir = get_cache_dir()
            video_tmp = os.path.join(cache_dir, f'{stamp}_video.tmp.mp4')
            audio_tmp = os.path.join(cache_dir, f'{stamp}_audio.tmp.m4a')
            tmp_files = [video_tmp, audio_tmp]

            # تصفير العدادات قبل البدء
            state['video_frac'] = 0.0
            state['audio_frac'] = 0.0

            # تحميل الفيديو والصوت في نفس الوقت (يوفر 40-50% من الزمن)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                v_future = executor.submit(download_stream, url, video_id, video_tmp, make_parallel_hook('video'))
                a_future = executor.submit(download_stream, url, audio_id, audio_tmp, make_parallel_hook('audio'))
                
                # الانتظار حتى ينتهي كلاهما. سيقوم برمي خطأ فوراً إذا تم الإلغاء
                for future in concurrent.futures.as_completed([v_future, a_future]):
                    future.result()

            # بمجرد انتهاء التحميل المتوازي، نبدأ الدمج
            report(95, 'Merging... (Please wait)')
            result = MediaMerger().mergeBlocking(service, video_tmp, audio_tmp, final_path)
            if result != 'SUCCESS':
                raise RuntimeError(f'Merge Error: {result}')

        scan_file(final_path)
        success = True
        report(100, 'Done')
        send(b'/done', final_path)

    except Exception as e:
        # فحص إذا كان الخطأ هو إلغاء التحميل
        err_str = str(e)
        cancelled = state['cancel'] or 'DownloadCancelled' in err_str
        if cancelled:
            send(b'/cancelled', 1)
        else:
            send(b'/error', err_str)

    finally:
        remove_quiet(*tmp_files)
        if not success and final_path:
            remove_quiet(final_path, final_path + '.part')
        state['busy'] = False
        state['cancel'] = False
        state['last_activity'] = time.time()
        state['stop_at'] = time.time() + 2
        
        # فصل الخيط عن JVM بأمان لمنع الانهيارات في أندرويد
        try:
            detach()
        except:
            pass


# ------------------------------------------------------------------ OSC handlers
def on_download(payload):
    state['last_activity'] = time.time()
    if state['busy']:
        send(b'/error', 'A download is already running.')
        return
    try:
        job = json.loads(payload)
    except Exception as e:
        send(b'/error', f'Bad job data: {e}')
        return
    state['stop_at'] = 0
    threading.Thread(target=run_job, args=(job,), daemon=True).start()

def on_cancel(*_):
    if state['busy'] and state['percent'] < 95:
        state['cancel'] = True

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
