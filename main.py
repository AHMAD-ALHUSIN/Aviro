import os
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

# --- Colors ---
BG_COLOR = get_color_from_hex('#12141A')
CARD_COLOR = get_color_from_hex('#1C1F27')
ACCENT_COLOR = get_color_from_hex('#FF4B4B')
ACCENT_COLOR_DARK = get_color_from_hex('#D63C3C')
TEXT_COLOR = get_color_from_hex('#F5F5F5')
SUBTEXT_COLOR = get_color_from_hex('#9AA0AC')


class YTDLogger:
    """Custom logger to prevent stdout crashes on Android"""
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
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[14])
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
        self.title = 'Video Downloader'
        Window.clearcolor = BG_COLOR

        self.format_map = {}

        # Top padding set to 110 to push the layout significantly down from the top bar
        root = BoxLayout(orientation='vertical', padding=[24, 110, 24, 20], spacing=16)

        # Header
        header = Label(
            text='Video & Audio Downloader',
            font_size='24sp',
            bold=True,
            color=TEXT_COLOR,
            size_hint=(1, None),
            height=36,
        )
        subheader = Label(
            text='Paste link, fetch qualities, then download',
            font_size='13sp',
            color=SUBTEXT_COLOR,
            size_hint=(1, None),
            height=22,
        )

        # Main Card Container
        card = Card(orientation='vertical', padding=16, spacing=12, size_hint=(1, None), height=260)

        self.url_input = TextInput(
            hint_text='Paste video URL here...',
            multiline=False,
            size_hint=(1, None),
            height=44,
            padding=[12, 10, 12, 10],
            background_color=(1, 1, 1, 0.06),
            foreground_color=TEXT_COLOR,
            hint_text_color=SUBTEXT_COLOR,
            cursor_color=ACCENT_COLOR,
        )

        self.fetch_btn = Button(
            text='1. Fetch Available Formats',
            font_size='14sp',
            bold=True,
            background_color=(0.2, 0.45, 0.75, 1),
            color=TEXT_COLOR,
            size_hint=(1, None),
            height=42,
        )
        self.fetch_btn.bind(on_press=self.start_fetch_formats)

        self.quality_spinner = Spinner(
            text='-- Select Format / Quality --',
            values=(),
            size_hint=(1, None),
            height=42,
            background_color=(0.15, 0.17, 0.22, 1),
            color=TEXT_COLOR,
        )

        self.download_btn = RoundedButton(
            text='2. Download Selected',
            font_size='15sp',
            bold=True,
            size_hint=(1, None),
            height=44,
            disabled=True,
        )
        self.download_btn.bind(on_press=self.start_download)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint=(1, None), height=8)

        card.add_widget(self.url_input)
        card.add_widget(self.fetch_btn)
        card.add_widget(self.quality_spinner)
        card.add_widget(self.download_btn)
        card.add_widget(self.progress_bar)

        # Status Label
        self.status_label = Label(
            text='Ready',
            font_size='14sp',
            color=SUBTEXT_COLOR,
            halign='center',
            valign='top',
            size_hint=(1, 1),
        )
        self.status_label.bind(size=self._update_label_text_size)

        root.add_widget(header)
        root.add_widget(subheader)
        root.add_widget(card)
        root.add_widget(self.status_label)
        root.add_widget(Widget())

        self.request_permissions()
        return root

    def _update_label_text_size(self, instance, size):
        instance.text_size = (size[0], None)

    def request_permissions(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.INTERNET,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                ])
            except Exception:
                pass

    def start_fetch_formats(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.set_status('Please paste a video URL first.')
            return

        self.set_status('Fetching available formats...')
        self.fetch_btn.disabled = True
        self.download_btn.disabled = True
        self.quality_spinner.values = ()
        self.quality_spinner.text = '-- Fetching... --'

        threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'logger': YTDLogger(),
                'nocheckcertificate': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])

                options = {}

                # Default fallback options
                options['[Video + Audio] Best Quality (No FFmpeg needed)'] = 'best[vcodec!=none][acodec!=none]/best'
                options['[Audio Only] Best Available Audio'] = 'bestaudio/best'

                # Extract progressive formats (Video + Audio combined in single stream)
                for f in formats:
                    vcodec = f.get('vcodec')
                    acodec = f.get('acodec')
                    ext = f.get('ext', 'mp4')
                    format_id = f.get('format_id')

                    # Case 1: Video + Audio together
                    if vcodec != 'none' and acodec != 'none':
                        height = f.get('height')
                        label_text = f"[Video + Audio] {height}p ({ext})" if height else f"[Video + Audio] {ext}"
                        options[label_text] = format_id

                    # Case 2: Audio Only
                    elif vcodec == 'none' and acodec != 'none':
                        abr = f.get('abr') or f.get('tbr')
                        label_text = f"[Audio Only] {int(abr)} kbps ({ext})" if abr else f"[Audio Only] ({ext})"
                        options[label_text] = format_id

                def _update_spinner(dt):
                    self.format_map = options
                    self.quality_spinner.values = list(options.keys())
                    if self.quality_spinner.values:
                        self.quality_spinner.text = self.quality_spinner.values[0]
                    self.set_status('Formats loaded! Select one and click Download.')
                    self.fetch_btn.disabled = False
                    self.download_btn.disabled = False

                Clock.schedule_once(_update_spinner)

        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f'Failed to fetch formats:\n{err}'))
            Clock.schedule_once(lambda dt: setattr(self.fetch_btn, 'disabled', False))

    def start_download(self, instance):
        url = self.url_input.text.strip()
        selected_text = self.quality_spinner.text

        if not url or selected_text not in self.format_map:
            self.set_status('Please select a valid format from the list.')
            return

        selected_format_id = self.format_map[selected_text]

        self.progress_bar.value = 0
        self.set_status('Preparing download...')
        self.download_btn.disabled = True
        self.fetch_btn.disabled = True

        threading.Thread(target=self.download_video, args=(url, selected_format_id), daemon=True).start()

    def get_save_directory(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity.getApplicationContext()
                ext_dir = context.getExternalFilesDir(None)
                if ext_dir is not None:
                    return ext_dir.getAbsolutePath()
            except Exception:
                pass
            return '/storage/emulated/0/Download'
        return os.getcwd()

    def progress_hook(self, d):
        if d.get('status') == 'downloading':
            percent_str = (d.get('_percent_str') or '').strip().replace('%', '')
            try:
                percent = float(percent_str)
            except ValueError:
                percent = None
            speed = (d.get('_speed_str') or '').strip()
            eta = (d.get('_eta_str') or '').strip()

            def _update(dt):
                if percent is not None:
                    self.progress_bar.value = percent
                self.set_status(f'Downloading... {percent_str}%  {speed}  ETA {eta}')

            Clock.schedule_once(_update)
        elif d.get('status') == 'finished':
            Clock.schedule_once(lambda dt: self.set_status('Finishing up...'))

    def set_status(self, text):
        self.status_label.text = text

    def download_video(self, url, format_id):
        try:
            save_dir = self.get_save_directory()
            save_path = os.path.join(save_dir, '%(title).100s.%(ext)s')

            ydl_opts = {
                'format': format_id,
                'outtmpl': save_path,
                'logger': YTDLogger(),
                'quiet': True,
                'no_warnings': True,
                'noprogress': False,
                'socket_timeout': 30,
                'retries': 5,
                'nocheckcertificate': True,
                'progress_hooks': [self.progress_hook],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            Clock.schedule_once(lambda dt: self.finish_success())
        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self.finish_error(err))

    def finish_success(self):
        self.progress_bar.value = 100
        self.set_status('Download complete! Saved inside the app folder.')
        self.download_btn.disabled = False
        self.fetch_btn.disabled = False

    def finish_error(self, err):
        self.set_status(f'Download failed:\n{err}')
        self.download_btn.disabled = False
        self.fetch_btn.disabled = False


if __name__ == '__main__':
    YTDownloaderApp().run()
