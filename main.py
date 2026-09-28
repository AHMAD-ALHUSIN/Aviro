import re
import json
import threading

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.core.clipboard import Clipboard
from kivy.utils import platform, get_color_from_hex

from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

# استيراد yt_dlp ثقيل (آلاف الملفات)، لذلك يُحمَّل في الخلفية بعد ظهور الواجهة
yt_dlp = None


def load_yt_dlp():
    global yt_dlp
    if yt_dlp is None:
        import yt_dlp as _yt_dlp
        yt_dlp = _yt_dlp
    return yt_dlp


# --- IPC with the download service ---
HOST = '127.0.0.1'
SERVICE_PORT = 3001   # الخدمة تستمع هنا
APP_PORT = 3002       # التطبيق يستمع هنا
SERVICE_CLASS = 'org.myapp.ytdownloader.ServiceDownloader'  # package.domain + package.name + Service + Name

# --- UI Colors ---
BG_COLOR = get_color_from_hex('#12141A')
CARD_COLOR = get_color_from_hex('#1C1F27')
ACCENT_COLOR = get_color_from_hex('#FF4B4B')
ACCENT_COLOR_DARK = get_color_from_hex('#D63C3C')
BTN_FETCH_COLOR = get_color_from_hex('#2A65C7')
TEXT_COLOR = get_color_from_hex('#F5F5F5')
SUBTEXT_COLOR = get_color_from_hex('#9AA0AC')
INPUT_COLOR = get_color_from_hex('#262A35')
DISABLED_COLOR = get_color_from_hex('#3A3F4B')

DOWNLOAD_TEXT = '2.  Download Now'
CANCEL_TEXT = 'Cancel Download'


class YTDLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def write(self, msg): pass


class RoundedButton(Button):
    """زر بحواف دائرية، يتغير لونه عند الضغط ويصبح رمادياً عند التعطيل."""
    def __init__(self, bg_color=ACCENT_COLOR, **kwargs):
        super().__init__(**kwargs)
        self._base = tuple(bg_color)
        self._dark = (bg_color[0] * 0.82, bg_color[1] * 0.82, bg_color[2] * 0.82, bg_color[3])
        self.background_normal = ''
        self.background_down = ''
        self.background_disabled_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT_COLOR
        self.disabled_color = SUBTEXT_COLOR
        with self.canvas.before:
            self._color_instr = Color(*self._base)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
        self.bind(pos=self._update_rect, size=self._update_rect)
        self.bind(state=self._update_color, disabled=self._update_color)
        self._update_color()

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_color(self, *_):
        if self.disabled:
            self._color_instr.rgba = DISABLED_COLOR
        elif self.state == 'down':
            self._color_instr.rgba = self._dark
        else:
            self._color_instr.rgba = self._base


class Card(BoxLayout):
    def __init__(self, bg_color=CARD_COLOR, radius=20, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class QualityOption(SpinnerOption):
    """عناصر القائمة المنسدلة للجودة بتصميم داكن وحجم مريح للمس."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0.17, 0.19, 0.26, 1)
        self.color = TEXT_COLOR
        self.font_size = sp(16)
        self.size_hint_y = None
        self.height = dp(50)


class YTDownloaderApp(App):
    def build(self):
        self.title = 'Media Downloader'
        Window.clearcolor = BG_COLOR
        Window.softinput_mode = 'below_target'  # لا تغطي لوحة المفاتيح حقل الرابط

        self.format_map = {}
        self.fetched_url = None
        self.video_title = 'Video'

        # حالة الخدمة
        self.ServiceCls = None
        self.PythonActivity = None
        self.service_error = None
        self.service_ready = False
        self.pending_job = None
        self.is_downloading = False
        self._cancelling = False
        self._ready_event = None
        self.osc = None
        self.osc_client = None

        root = BoxLayout(orientation='vertical', padding=[dp(20), dp(16), dp(20), dp(16)])

        # مساحة علوية أصغر من السفلية => المحتوى أعلى منتصف الشاشة قليلاً
        root.add_widget(Widget(size_hint_y=0.7))

        header = Label(text='Video Downloader', font_size=sp(30), bold=True, color=TEXT_COLOR,
                       size_hint=(1, None), height=dp(46))
        subheader = Label(text='Paste link, select quality, and download', font_size=sp(14),
                          color=SUBTEXT_COLOR, size_hint=(1, None), height=dp(26))
        root.add_widget(header)
        root.add_widget(subheader)
        root.add_widget(Widget(size_hint_y=None, height=dp(22)))

        card = Card(orientation='vertical', padding=dp(20), spacing=dp(16), size_hint=(1, None))
        card.bind(minimum_height=card.setter('height'))

        # --- صف الرابط + زر لصق ---
        input_row = Card(bg_color=INPUT_COLOR, radius=14, orientation='horizontal',
                         size_hint=(1, None), height=dp(58), padding=[dp(14), 0, dp(6), 0], spacing=dp(6))
        self.url_input = TextInput(hint_text='Paste URL here...', multiline=False, font_size=sp(16),
                                   background_normal='', background_active='', background_color=(0, 0, 0, 0),
                                   foreground_color=TEXT_COLOR, hint_text_color=SUBTEXT_COLOR,
                                   cursor_color=ACCENT_COLOR, padding=[0, dp(18), 0, dp(18)])
        paste_btn = Button(text='Paste', font_size=sp(15), bold=True, size_hint=(None, 1), width=dp(72),
                           background_normal='', background_down='', background_color=(0, 0, 0, 0),
                           color=ACCENT_COLOR)
        paste_btn.bind(on_press=self.paste_from_clipboard)
        input_row.add_widget(self.url_input)
        input_row.add_widget(paste_btn)

        self.fetch_btn = RoundedButton(text='1.  Fetch Qualities', font_size=sp(17), bold=True,
                                       bg_color=BTN_FETCH_COLOR, size_hint=(1, None), height=dp(58))
        self.fetch_btn.bind(on_press=self.start_fetch_formats)

        self.quality_spinner = Spinner(text='-- Select Quality --', values=(), font_size=sp(16),
                                       size_hint=(1, None), height=dp(58), option_cls=QualityOption,
                                       background_normal='', background_down='',
                                       background_color=INPUT_COLOR, color=TEXT_COLOR)

        self.download_btn = RoundedButton(text=DOWNLOAD_TEXT, font_size=sp(18), bold=True,
                                          bg_color=ACCENT_COLOR, size_hint=(1, None), height=dp(64), disabled=True)
        self.download_btn.bind(on_press=self.on_download_pressed)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint=(1, None), height=dp(10))

        card.add_widget(input_row)
        card.add_widget(self.fetch_btn)
        card.add_widget(self.quality_spinner)
        card.add_widget(self.download_btn)
        card.add_widget(self.progress_bar)
        root.add_widget(card)

        self.status_label = Label(text='Ready', font_size=sp(14), color=SUBTEXT_COLOR, halign='center',
                                  valign='top', size_hint=(1, None), height=dp(90))
        self.status_label.bind(size=lambda inst, size: setattr(inst, 'text_size', (size[0], None)))

        root.add_widget(Widget(size_hint_y=None, height=dp(14)))
        root.add_widget(self.status_label)
        root.add_widget(Widget(size_hint_y=1.3))

        self.request_permissions()
        return root

    # ------------------------------------------------------------ lifecycle
    def on_start(self):
        # تحميل yt_dlp في الخلفية حتى تظهر الواجهة فوراً
        threading.Thread(target=lambda: load_yt_dlp(), daemon=True).start()

        # قناة الاتصال مع الخدمة (OSC)
        self.osc = OSCThreadServer(encoding='utf8')
        self.osc.listen(HOST, port=APP_PORT, default=True)
        self.osc.bind(b'/ready', self._osc_ready)
        self.osc.bind(b'/state', self._osc_state)
        self.osc.bind(b'/progress', self._osc_progress)
        self.osc.bind(b'/done', self._osc_done)
        self.osc.bind(b'/cancelled', self._osc_cancelled)
        self.osc.bind(b'/error', self._osc_error)
        self.osc_client = OSCClient(HOST, SERVICE_PORT, encoding='utf8')

        if platform != 'android':
            return
        try:
            # كلاسات جافا تُحمَّل في الخيط الرئيسي فقط
            from jnius import autoclass
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.ServiceCls = autoclass(SERVICE_CLASS)
        except Exception as e:
            self.service_error = str(e)
            self.set_status(f'Service load failed:\n{e}')
            return

        # إذا كانت الخدمة تعمل (تنزيل جارٍ) نستعيد الحالة
        self.send_to_service(b'/sync', 1)

    def on_stop(self):
        try:
            if self.osc:
                self.osc.stop_all()
        except Exception:
            pass

    def on_pause(self):
        return True  # يبقي التطبيق حياً عند الخروج منه

    def on_resume(self):
        if platform == 'android':
            self.send_to_service(b'/sync', 1)

    def request_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.INTERNET,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                    'android.permission.POST_NOTIFICATIONS',
                ])
            except Exception:
                pass

    # ------------------------------------------------------------ service IPC
    def send_to_service(self, path, *args):
        try:
            self.osc_client.send_message(path, list(args))
        except Exception as e:
            print('OSC send failed:', e)

    def start_service(self):
        self.ServiceCls.start(self.PythonActivity.mActivity, '')

    def _osc_ready(self, *_):
        def _do(dt):
            self.service_ready = True
            if self._ready_event:
                self._ready_event.cancel()
                self._ready_event = None
            if self.pending_job is not None:
                job, self.pending_job = self.pending_job, None
                self.set_status('Starting download...')
                self.send_to_service(b'/download', json.dumps(job))
        Clock.schedule_once(_do)

    def _osc_state(self, busy, percent, text):
        def _do(dt):
            if busy:
                self.set_busy(True)
                self.progress_bar.value = percent
                self.set_status(text or 'Downloading...')
        Clock.schedule_once(_do)

    def _osc_progress(self, percent, text):
        def _do(dt):
            if not self.is_downloading:
                self.set_busy(True)
            self.progress_bar.value = percent
            self.set_status(text)
            # لا يمكن الإلغاء أثناء الدمج
            if not self._cancelling:
                self.download_btn.disabled = percent >= 95
        Clock.schedule_once(_do)

    def _osc_done(self, path):
        Clock.schedule_once(lambda dt: self.finish_success())

    def _osc_cancelled(self, *_):
        Clock.schedule_once(lambda dt: self.finish_cancelled())

    def _osc_error(self, msg):
        Clock.schedule_once(lambda dt: self.finish_error(msg))

    def _on_ready_timeout(self, dt):
        if self.pending_job is not None:
            self.pending_job = None
            self.finish_error('Background service did not start.\nCheck notification permission and try again.')

    # ------------------------------------------------------------ UI actions
    def paste_from_clipboard(self, instance):
        try:
            text = Clipboard.paste()
            if text:
                self.url_input.text = text.strip()
        except Exception:
            pass

    def start_fetch_formats(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.set_status('Please paste a video URL first.')
            return
        self.set_status('Fetching qualities...')
        self.fetch_btn.disabled = True
        self.download_btn.disabled = True
        self.quality_spinner.values = ()
        self.quality_spinner.text = '-- Fetching... --'
        threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        try:
            load_yt_dlp()
            ydl_opts = {'quiet': True, 'no_warnings': True, 'logger': YTDLogger(), 'nocheckcertificate': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                options = {}
                title = info.get('title') or 'Video'

                # الدمج مسموح ليوتيوب فقط؛ باقي المنصات تحميل مباشر بدون دمج
                extractor = (info.get('extractor_key') or info.get('extractor') or '').lower()
                is_youtube = 'youtube' in extractor or 'youtu' in url.lower()

                # 1. تحديد أفضل مسار صوتي من نوع m4a أو أفضل صوت متاح
                audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
                audio_formats.sort(key=lambda x: x.get('tbr') or x.get('abr') or 0)

                m4a_audio = [f for f in audio_formats if f.get('ext') == 'm4a']
                best_audio = m4a_audio[-1] if m4a_audio else (audio_formats[-1] if audio_formats else None)
                best_audio_id = best_audio['format_id'] if best_audio else None

                # 2. تصفية مسارات الفيديو وحفظ أفضل مسار لكل دقة (1080p, 720p, ...)
                height_map = {}
                for f in formats:
                    vcodec = f.get('vcodec')
                    height = f.get('height')
                    if vcodec != 'none' and height and isinstance(height, int):
                        # غير يوتيوب: نتجاهل الفيديو بدون صوت (لأنه يحتاج دمج)
                        if not is_youtube and f.get('acodec') == 'none':
                            continue
                        if height not in height_map:
                            height_map[height] = f
                        else:
                            curr = height_map[height]
                            # إعطاء أولوية لصيغة mp4 أو معدل نقل البت الأعلى
                            if (f.get('ext') == 'mp4' and curr.get('ext') != 'mp4') or ((f.get('tbr') or 0) > (curr.get('tbr') or 0)):
                                height_map[height] = f

                # 3. ترتيب الجودات تنازلياً وإنشاء التسميات النظيفة
                sorted_heights = sorted(height_map.keys(), reverse=True)
                for h in sorted_heights:
                    f = height_map[h]
                    acodec = f.get('acodec')
                    format_id = f.get('format_id')

                    label = f"{h}p"
                    if h >= 1080: label += " (Full HD)"
                    elif h >= 720: label += " (HD)"

                    if acodec != 'none':
                        options[label] = (format_id, None)
                    elif best_audio_id and is_youtube:
                        options[label] = (format_id, best_audio_id)

                # غير يوتيوب ولا توجد صيغة جاهزة بالدقة: أفضل ملف واحد متاح
                if not is_youtube and not options:
                    options["Best Available"] = ('best', None)

                # تحميل الصوت فقط (إن وُجد مسار صوتي)
                if best_audio_id:
                    options["Audio Only (M4A)"] = (None, best_audio_id)

                def _update_spinner(dt):
                    self.format_map = options
                    self.fetched_url = url
                    self.video_title = title
                    self.quality_spinner.values = list(options.keys())
                    if self.quality_spinner.values:
                        self.quality_spinner.text = self.quality_spinner.values[0]
                    self.set_status('Qualities loaded. Select quality and tap Download.')
                    self.fetch_btn.disabled = False
                    self.download_btn.disabled = False

                Clock.schedule_once(_update_spinner)
        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): self.set_status(f'Error:\n{err}'))
            Clock.schedule_once(lambda dt: setattr(self.fetch_btn, 'disabled', False))

    def on_download_pressed(self, instance):
        if self.is_downloading:
            self.cancel_download()
        else:
            self.start_download()

    def start_download(self):
        if platform != 'android':
            self.set_status('Downloads run in the background service (Android only).')
            return
        if self.ServiceCls is None:
            self.set_status(f'Background service unavailable:\n{self.service_error}')
            return

        url = self.url_input.text.strip()
        selected_text = self.quality_spinner.text
        if not url or selected_text not in self.format_map:
            self.set_status('Please select a valid quality option.')
            return
        if url != self.fetched_url:
            self.set_status('URL changed. Tap "Fetch Qualities" again.')
            return

        video_id, audio_id = self.format_map[selected_text]
        job = {'url': url, 'video_id': video_id, 'audio_id': audio_id, 'title': self.video_title}

        self._cancelling = False
        self.progress_bar.value = 0
        self.set_busy(True)

        if self.service_ready:
            self.set_status('Starting download...')
            self.send_to_service(b'/download', json.dumps(job))
        else:
            # تشغيل الخدمة أولاً، وسيُرسل العمل عند وصول /ready
            self.set_status('Starting background service...')
            self.pending_job = job
            try:
                self.start_service()
            except Exception as e:
                self.pending_job = None
                self.finish_error(f'Could not start service: {e}')
                return
            self._ready_event = Clock.schedule_once(self._on_ready_timeout, 25)

    def cancel_download(self):
        self._cancelling = True
        self.download_btn.disabled = True
        self.set_status('Cancelling...')
        if self.pending_job is not None:
            # لم يبدأ فعلياً بعد
            self.pending_job = None
            if self._ready_event:
                self._ready_event.cancel()
                self._ready_event = None
            self.finish_cancelled()
        else:
            self.send_to_service(b'/cancel', 1)

    # ------------------------------------------------------------ UI state
    def set_busy(self, busy):
        self.is_downloading = busy
        self.fetch_btn.disabled = busy
        self.download_btn.text = CANCEL_TEXT if busy else DOWNLOAD_TEXT
        self.download_btn.disabled = False

    def set_status(self, text):
        self.status_label.text = text

    def finish_success(self):
        self.service_ready = False  # الخدمة تُغلق نفسها بعد الانتهاء
        self._cancelling = False
        self.progress_bar.value = 100
        self.set_status('Download complete! Saved in Downloads folder.')
        self.set_busy(False)

    def finish_cancelled(self):
        self.service_ready = False
        self._cancelling = False
        self.progress_bar.value = 0
        self.set_status('Download cancelled.')
        self.set_busy(False)

    def finish_error(self, err):
        self.service_ready = False
        self._cancelling = False
        self.set_status(f'Failed:\n{err}')
        self.set_busy(False)


if __name__ == '__main__':
    YTDownloaderApp().run()
