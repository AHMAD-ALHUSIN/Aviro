import os
import threading

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
from kivy.utils import platform, get_color_from_hex

import yt_dlp

# --- colors ---
BG_COLOR = get_color_from_hex('#12141A')
CARD_COLOR = get_color_from_hex('#1C1F27')
ACCENT_COLOR = get_color_from_hex('#FF4B4B')
ACCENT_COLOR_DARK = get_color_from_hex('#D63C3C')
TEXT_COLOR = get_color_from_hex('#F5F5F5')
SUBTEXT_COLOR = get_color_from_hex('#9AA0AC')


class YTDLogger:
    """كائن مخصص للتسجيل يمنع خطأ AttributeError على بيئة أندرويد."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def write(self, msg): pass  # يمنع خطأ 'str' object has no attribute 'write'


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

        root = BoxLayout(orientation='vertical', padding=24, spacing=18)

        header = Label(
            text='Video Downloader',
            font_size='26sp',
            bold=True,
            color=TEXT_COLOR,
            size_hint=(1, None),
            height=48,
        )
        subheader = Label(
            text='Paste a video link and download it in the best available quality',
            font_size='14sp',
            color=SUBTEXT_COLOR,
            size_hint=(1, None),
            height=28,
        )

        card = Card(orientation='vertical', padding=20, spacing=16, size_hint=(1, None), height=180)

        self.url_input = TextInput(
            hint_text='Paste video URL here...',
            multiline=False,
            size_hint=(1, None),
            height=48,
            padding=[14, 12, 14, 12],
            background_color=(1, 1, 1, 0.06),
            foreground_color=TEXT_COLOR,
            hint_text_color=SUBTEXT_COLOR,
            cursor_color=ACCENT_COLOR,
        )

        self.download_btn = RoundedButton(
            text='Download',
            font_size='16sp',
            bold=True,
            size_hint=(1, None),
            height=48,
        )
        self.download_btn.bind(on_press=self.start_download)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint=(1, None), height=8)

        card.add_widget(self.url_input)
        card.add_widget(self.download_btn)
        card.add_widget(self.progress_bar)

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

    def start_download(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.set_status('Please paste a video URL first.')
            return

        self.progress_bar.value = 0
        self.set_status('Preparing download...')
        self.download_btn.disabled = True

        threading.Thread(target=self.download_video, args=(url,), daemon=True).start()

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

    def download_video(self, url):
        try:
            save_dir = self.get_save_directory()
            save_path = os.path.join(save_dir, '%(title).100s.%(ext)s')

            ydl_opts = {
                # تجربة أفضل جودة مدمجة أولاً، ثم التراجع لأي صيغة متوفرة عند عدم وجود أفضل جودة
                'format': 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
                'outtmpl': save_path,
                'logger': YTDLogger(),  # حماية التسجيل لمنع انهيار البرنامج
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

    def finish_error(self, err):
        self.set_status(f'Download failed:\n{err}')
        self.download_btn.disabled = False


if __name__ == '__main__':
    YTDownloaderApp().run()
