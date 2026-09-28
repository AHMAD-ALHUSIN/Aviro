import os
import json
import time
import threading

from jnius import autoclass
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

import yt_dlp

HOST = '127.0.0.1'
SERVICE_PORT = 3001   # الخدمة تستمع هنا
APP_PORT = 3002       # التطبيق يستمع هنا
IDLE_TIMEOUT = 60     # تتوقف الخدمة إذا لم يصلها عمل خلال 60 ثانية

# كلاسات جافا تُحمَّل هنا (خيط الخدمة الرئيسي) لأن ClassLoader يرى كلاسات التطبيق هنا فقط
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

state = {
    'busy': False,
    'cancel': False,
    'percent': 0.0,
    'text': '',
    'last_activity': time.time(),
    'stop_at': 0,
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
    """Progress hook يحوّل تقدم المرحلة إلى نسبة من (lo..hi) من الإجمالي."""
    last = [0.0]

    def hook(d):
        if state['cancel']:
            raise yt_dlp.utils.DownloadCancelled()
        if d.get('status') != 'downloading':
            return
        now = time.time()
        if now - last[0] < 0.3:
            return
        last[0] = now

        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        done = d.get('downloaded_bytes') or 0
        if total:
            frac = min(done / total, 1.0)
        elif d.get('fragment_count'):
            frac = min((d.get('fragment_index') or 0) / d['fragment_count'], 1.0)
        else:
            frac = 0.0

        speed = fmt_speed(d.get('speed'))
        text = f'{label} {frac * 100:.0f}%'
        if speed:
            text += f' | {speed}'
        report(lo + (hi - lo) * frac, text)

    return hook


def download_stream(url, fmt, out_path, hook):
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
            # صوت فقط
            final_path = unique_path(save_dir, title, 'm4a')
            download_stream(url, audio_id, final_path, make_hook(0, 100, 'Downloading audio'))

        elif audio_id is None:
            # ملف جاهز (فيديو + صوت) بدون دمج
            final_path = unique_path(save_dir, title, 'mp4')
            download_stream(url, video_id, final_path, make_hook(0, 100, 'Downloading'))

        else:
            # فيديو وصوت منفصلان: تنزيل مؤقت ثم دمج بـ Media3
            if MediaMerger is None:
                raise RuntimeError(f'MediaMerger not loaded: {MERGER_ERROR}')

            final_path = unique_path(save_dir, title, 'mp4')
            stamp = int(time.time())
            cache_dir = get_cache_dir()
            video_tmp = os.path.join(cache_dir, f'{stamp}_video.tmp.mp4')
            audio_tmp = os.path.join(cache_dir, f'{stamp}_audio.tmp.m4a')
            tmp_files = [video_tmp, audio_tmp]

            download_stream(url, video_id, video_tmp, make_hook(0, 75, 'Downloading video'))
            download_stream(url, audio_id, audio_tmp, make_hook(75, 95, 'Downloading audio'))

            report(95, 'Merging... (Please wait)')
            result = MediaMerger().mergeBlocking(service, video_tmp, audio_tmp, final_path)
            if result != 'SUCCESS':
                raise RuntimeError(f'Merge Error: {result}')

        scan_file(final_path)
        success = True
        report(100, 'Done')
        send(b'/done', final_path)

    except Exception as e:
        cancelled = state['cancel'] or isinstance(e, yt_dlp.utils.DownloadCancelled)
        if cancelled:
            send(b'/cancelled', 1)
        else:
            send(b'/error', str(e))

    finally:
        remove_quiet(*tmp_files)
        if not success and final_path:
            remove_quiet(final_path, final_path + '.part')
        state['busy'] = False
        state['cancel'] = False
        state['last_activity'] = time.time()
        state['stop_at'] = time.time() + 2   # توقف الخدمة بعد ثانيتين من الانتهاء


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
    # لا يمكن الإلغاء أثناء الدمج
    if state['busy'] and state['percent'] < 95:
        state['cancel'] = True


def on_sync(*_):
    """يستدعيها التطبيق عند فتحه ليعرف حالة الخدمة."""
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
