import os
import re
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

import yt_dlp

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

        # كلاسات جافا تُحمَّل في الخيط الرئيسي فقط (انظر on_start)
        self.PythonActivity = None
        self.MediaMerger = None
        self.merger_error = None

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

        self.download_btn = RoundedButton(text='2.  Download Now', font_size=sp(18), bold=True,
                                          bg_color=ACCENT_COLOR, size_hint=(1, None), height=dp(64), disabled=True)
        self.download_btn.bind(on_press=self.start_download)

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

    def paste_from_clipboard(self, instance):
        try:
            text = Clipboard.paste()
            if text:
                self.url_input.text = text.strip()
        except Exception:
            pass

    def on_start(self):
        """تحميل كلاسات جافا في الخيط الرئيسي (هنا يرى الـ ClassLoader كلاسات التطبيق)."""
        if platform != 'android':
            return
        try:
            from jnius import autoclass
            self.PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.MediaMerger = autoclass('org.myapp.MediaMerger')
            print('MediaMerger loaded OK on main thread')
        except Exception as e:
            self.merger_error = str(e)
            print('MediaMerger load FAILED:', e)
            self.set_status(f'MediaMerger load failed:\n{e}')

    def request_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
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
            ydl_opts = {'quiet': True, 'no_warnings': True, 'logger': YTDLogger(), 'nocheckcertificate': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                options = {}

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

    def start_download(self, instance):
        url = self.url_input.text.strip()
        selected_text = self.quality_spinner.text
        if not url or selected_text not in self.format_map:
            self.set_status('Please select a valid quality option.')
            return

        format_tuple = self.format_map[selected_text]
        self.progress_bar.value = 0
        self.set_status('Preparing download...')
        self.download_btn.disabled = True
        self.fetch_btn.disabled = True

        threading.Thread(target=self.download_video, args=(url, format_tuple), daemon=True).start()

    def get_save_directory(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                Environment = autoclass('android.os.Environment')
                download_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                if download_dir is not None:
                    return download_dir.getAbsolutePath()
            except Exception:
                pass
            return '/storage/emulated/0/Download'
        return os.getcwd()

    def scan_file_to_gallery(self, file_path):
        if platform == 'android' and self.PythonActivity is not None:
            try:
                from jnius import autoclass
                MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
                context = self.PythonActivity.mActivity.getApplicationContext()
                MediaScannerConnection.scanFile(context, [file_path], None, None)
            except Exception:
                pass

    def progress_hook(self, d):
        if d.get('status') == 'downloading':
            raw_percent = d.get('_percent_str', '')
            clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', raw_percent).replace('%', '').strip()
            try:
                percent = float(clean_percent)
            except ValueError:
                percent = None

            raw_speed = d.get('_speed_str', '')
            speed = re.sub(r'\x1b\[[0-9;]*m', '', raw_speed).strip()

            def _update(dt):
                if percent is not None:
                    self.progress_bar.value = percent
                self.set_status(f'Downloading... {clean_percent}% | {speed}')
            Clock.schedule_once(_update)

        elif d.get('status') == 'finished':
            Clock.schedule_once(lambda dt: self.set_status('Stream downloaded. Processing...'))

    def download_video(self, url, format_tuple):
        try:
            video_id, audio_id = format_tuple
            save_dir = self.get_save_directory()

            with yt_dlp.YoutubeDL({'quiet': True, 'logger': YTDLogger(), 'nocheckcertificate': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                raw_title = info.get('title', 'Video')
                safe_title = "".join([c for c in raw_title if c.isalnum() or c in (' ', '_', '-')]).rstrip()
                if not safe_title: safe_title = "Video"

            # خيار تحميل الصوت فقط
            if video_id is None and audio_id is not None:
                final_path = os.path.join(save_dir, f"{safe_title}.m4a")
                ydl_opts = {
                    'format': audio_id, 'outtmpl': final_path, 'quiet': True,
                    'logger': YTDLogger(), 'nocheckcertificate': True, 'progress_hooks': [self.progress_hook]
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                self.scan_file_to_gallery(final_path)
                Clock.schedule_once(lambda dt: self.finish_success())
                return

            final_path = os.path.join(save_dir, f"{safe_title}.mp4")

            # ملف فيديو وصوت جاهز مسبقاً بدون دمج
            if audio_id is None:
                ydl_opts = {
                    'format': video_id, 'outtmpl': final_path, 'quiet': True,
                    'logger': YTDLogger(), 'nocheckcertificate': True, 'progress_hooks': [self.progress_hook]
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                self.scan_file_to_gallery(final_path)
                Clock.schedule_once(lambda dt: self.finish_success())
                return

            # فيديو وصوت منفصلان (تحميل مؤقت ثم الدمج بـ Media3)
            if platform == 'android':
                if self.PythonActivity is None:
                    raise RuntimeError(f'PythonActivity not loaded: {self.merger_error}')
                cache_dir = self.PythonActivity.mActivity.getExternalCacheDir().getAbsolutePath()
            else:
                cache_dir = os.getcwd()

            video_tmp = os.path.join(cache_dir, "video.tmp.mp4")
            audio_tmp = os.path.join(cache_dir, "audio.tmp.m4a")

            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp):
                    try: os.remove(tmp)
                    except Exception: pass

            Clock.schedule_once(lambda dt: self.set_status('Downloading Video stream...'))
            with yt_dlp.YoutubeDL({'format': video_id, 'outtmpl': video_tmp, 'quiet': True, 'nocheckcertificate': True, 'logger': YTDLogger(), 'progress_hooks': [self.progress_hook]}) as ydl:
                ydl.download([url])

            Clock.schedule_once(lambda dt: self.set_status('Downloading Audio stream...'))
            with yt_dlp.YoutubeDL({'format': audio_id, 'outtmpl': audio_tmp, 'quiet': True, 'nocheckcertificate': True, 'logger': YTDLogger()}) as ydl:
                ydl.download([url])

            Clock.schedule_once(lambda dt: self.set_status('Merging with Media3... (Please wait)'))

            if platform == 'android':
                # نستخدم الكلاس المحمّل مسبقاً في الخيط الرئيسي (لا autoclass هنا)
                if self.MediaMerger is None:
                    raise RuntimeError(f'MediaMerger class was not loaded at startup: {self.merger_error}')

                merger = self.MediaMerger()
                result = merger.mergeBlocking(self.PythonActivity.mActivity, video_tmp, audio_tmp, final_path)

                if result == "SUCCESS":
                    self.scan_file_to_gallery(final_path)
                    Clock.schedule_once(lambda dt: self.finish_success())
                else:
                    Clock.schedule_once(lambda dt, r=result: self.finish_error(f'Merge Error: {r}'))
            else:
                Clock.schedule_once(lambda dt: self.finish_error("Merging is only supported on Android devices."))

            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp):
                    try: os.remove(tmp)
                    except Exception: pass

        except Exception as e:
            Clock.schedule_once(lambda dt, err=str(e): self.finish_error(err))

    def set_status(self, text):
        self.status_label.text = text

    def finish_success(self):
        self.progress_bar.value = 100
        self.set_status('Download complete! Saved in Downloads folder.')
        self.download_btn.disabled = False
        self.fetch_btn.disabled = False

    def finish_error(self, err):
        self.set_status(f'Failed:\n{err}')
        self.download_btn.disabled = False
        self.fetch_btn.disabled = False


if __name__ == '__main__':
    YTDownloaderApp().run()
