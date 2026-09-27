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
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
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


class YTDLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def write(self, msg): pass


class RoundedButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT_COLOR
        with self.canvas.before:
            self._color_instr = Color(*ACCENT_COLOR)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self._update_rect, size=self._update_rect)
        self.bind(state=self._update_state_color)

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_state_color(self, *_):
        self._color_instr.rgba = ACCENT_COLOR_DARK if self.state == 'down' else ACCENT_COLOR


class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*CARD_COLOR)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[18])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class YTDownloaderApp(App):
    def build(self):
        self.title = 'Media Downloader'
        Window.clearcolor = BG_COLOR
        self.format_map = {}

        root = BoxLayout(orientation='vertical', padding=[20, 20, 20, 20])
        root.add_widget(Widget(size_hint_y=1))

        header = Label(text='Video Downloader', font_size='26sp', bold=True, color=TEXT_COLOR, size_hint=(1, None), height=38)
        subheader = Label(text='Paste link, select quality, and download', font_size='13sp', color=SUBTEXT_COLOR, size_hint=(1, None), height=24)
        root.add_widget(header)
        root.add_widget(subheader)
        root.add_widget(Widget(size_hint_y=None, height=14))

        card = Card(orientation='vertical', padding=20, spacing=14, size_hint=(1, None), height=290)
        
        self.url_input = TextInput(hint_text='Paste URL here...', multiline=False, size_hint=(1, None), height=46,
                                   padding=[12, 11, 12, 11], background_color=(1, 1, 1, 0.06), foreground_color=TEXT_COLOR,
                                   hint_text_color=SUBTEXT_COLOR, cursor_color=ACCENT_COLOR)
        
        self.fetch_btn = Button(text='1. Fetch Qualities', font_size='14sp', bold=True, background_normal='',
                                background_color=BTN_FETCH_COLOR, color=TEXT_COLOR, size_hint=(1, None), height=46)
        self.fetch_btn.bind(on_press=self.start_fetch_formats)
        
        self.quality_spinner = Spinner(text='-- Select Quality --', values=(), size_hint=(1, None), height=44,
                                       background_normal='', background_color=(0.14, 0.16, 0.22, 1), color=TEXT_COLOR)
        
        self.download_btn = RoundedButton(text='2. Download Now', font_size='15sp', bold=True, size_hint=(1, None), height=48, disabled=True)
        self.download_btn.bind(on_press=self.start_download)
        
        self.progress_bar = ProgressBar(max=100, value=0, size_hint=(1, None), height=8)

        card.add_widget(self.url_input)
        card.add_widget(self.fetch_btn)
        card.add_widget(self.quality_spinner)
        card.add_widget(self.download_btn)
        card.add_widget(self.progress_bar)
        root.add_widget(card)

        self.status_label = Label(text='Ready', font_size='13sp', color=SUBTEXT_COLOR, halign='center', valign='top', size_hint=(1, None), height=60)
        self.status_label.bind(size=lambda inst, size: setattr(inst, 'text_size', (size[0], None)))
        
        root.add_widget(Widget(size_hint_y=None, height=10))
        root.add_widget(self.status_label)
        root.add_widget(Widget(size_hint_y=1))

        self.request_permissions()
        return root

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
                    elif best_audio_id:
                        options[label] = (format_id, best_audio_id)

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
            Clock.schedule_once(lambda dt: self.set_status(f'Error:\n{str(e)}'))
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
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
                context = PythonActivity.mActivity.getApplicationContext()
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
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                cache_dir = PythonActivity.mActivity.getExternalCacheDir().getAbsolutePath()
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
                from jnius import autoclass
                MediaMerger = autoclass('org.myapp.MediaMerger')
                merger = MediaMerger()
                result = merger.mergeBlocking(PythonActivity.mActivity, video_tmp, audio_tmp, final_path)
                
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
