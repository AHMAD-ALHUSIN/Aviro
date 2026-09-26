import sys
import io
import os
import threading

if not hasattr(sys.stdout, 'write'):
    sys.stdout = io.StringIO()
if not hasattr(sys.stderr, 'write'):
    sys.stderr = io.StringIO()

os.environ['KIVY_NO_ENV_CONFIG'] = '1'
os.environ['KIVY_LOG_MODE'] = 'PYTHON'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget
from kivy.clock import mainthread, Clock
from kivy.utils import platform, get_color_from_hex
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.core.window import Window
from kivy.metrics import dp

Window.clearcolor = get_color_from_hex("#0f0f1a")

yt_dlp = None

# ---- ألوان التصميم ----
C_BG       = "#0f0f1a"
C_CARD     = "#1a1a2e"
C_PRIMARY  = "#3b82f6"
C_SUCCESS  = "#22c55e"
C_DANGER   = "#ef4444"
C_TEXT     = "#f1f5f9"
C_SUBTEXT  = "#94a3b8"
C_BORDER   = "#334155"


def hex_color(h, a=1):
    c = get_color_from_hex(h)
    return (c[0], c[1], c[2], a)


class Card(BoxLayout):
    """بطاقة بخلفية مستديرة الزوايا"""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.padding = [dp(20), dp(20)]
        self.spacing = dp(14)
        self.orientation = "vertical"
        with self.canvas.before:
            Color(*hex_color(C_CARD))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size


def styled_button(text, bg=C_PRIMARY, disabled=False):
    btn = Button(
        text=text,
        size_hint_y=None,
        height=dp(52),
        font_size=dp(15),
        color=hex_color(C_TEXT),
        background_normal="",
        background_down="",
        background_color=hex_color(bg, 0 if disabled else 1),
        disabled=disabled,
    )
    # تأثير hover / press
    def on_state(b, state):
        if state == "down":
            b.background_color = hex_color(bg, 0.7)
        else:
            b.background_color = hex_color(bg, 1 if not b.disabled else 0.4)
    btn.bind(state=on_state)
    return btn


def styled_label(text, color=C_TEXT, size=15, bold=False):
    return Label(
        text=text,
        color=hex_color(color),
        font_size=dp(size),
        bold=bold,
        size_hint_y=None,
        height=dp(size + 10),
    )


class _QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def get_download_dir():
    if platform == "android":
        from android.storage import primary_external_storage_path
        path = os.path.join(primary_external_storage_path(), "Download", "YTDownloader")
    else:
        path = os.path.join(os.path.expanduser("~"), "Downloads", "YTDownloader")
    os.makedirs(path, exist_ok=True)
    return path


class DownloaderApp(App):
    def build(self):
        self.title = "Video Downloader"
        self._ytdlp_ready = False

        # الجذر
        root = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(32), dp(16), dp(16)],
            spacing=dp(16),
        )

        # ---- عنوان ----
        root.add_widget(styled_label("⬇  Video Downloader", color=C_TEXT, size=22, bold=True))
        root.add_widget(styled_label("Paste a link, pick quality, download.", color=C_SUBTEXT, size=13))
        root.add_widget(Widget(size_hint_y=None, height=dp(8)))

        # ---- بطاقة الإدخال ----
        card = Card(size_hint_y=None, height=dp(260))

        self.url_input = TextInput(
            hint_text="https://youtube.com/watch?v=...",
            hint_text_color=hex_color(C_SUBTEXT),
            foreground_color=hex_color(C_TEXT),
            background_color=hex_color(C_BORDER, 0.4),
            cursor_color=hex_color(C_PRIMARY),
            size_hint_y=None,
            height=dp(52),
            multiline=False,
            padding=[dp(12), dp(14)],
            font_size=dp(13),
        )
        card.add_widget(self.url_input)

        self.check_btn = styled_button("Check Available Qualities", bg=C_PRIMARY, disabled=True)
        self.check_btn.bind(on_release=self.check_formats)
        card.add_widget(self.check_btn)

        self.quality_spinner = Spinner(
            text="Select Quality",
            values=[],
            size_hint_y=None,
            height=dp(48),
            font_size=dp(14),
            color=hex_color(C_TEXT),
            background_normal="",
            background_color=hex_color(C_BORDER, 0.6),
            disabled=True,
        )
        card.add_widget(self.quality_spinner)

        self.download_btn = styled_button("Download", bg=C_SUCCESS, disabled=True)
        self.download_btn.bind(on_release=self.download_video)
        card.add_widget(self.download_btn)

        root.add_widget(card)

        # ---- شريط التقدم ----
        self.progress = ProgressBar(
            max=100, value=0,
            size_hint_y=None, height=dp(8),
        )
        root.add_widget(self.progress)

        # ---- حالة ----
        self.status_label = Label(
            text="Loading...",
            color=hex_color(C_SUBTEXT),
            font_size=dp(13),
            size_hint_y=None,
            height=dp(60),
            text_size=(Window.width - dp(32), None),
            halign="center",
        )
        root.add_widget(self.status_label)

        root.add_widget(Widget())  # spacer

        if platform == "android":
            self.request_android_permissions()

        Clock.schedule_once(self._load_ytdlp_async, 0.1)
        return root

    def _load_ytdlp_async(self, dt):
        threading.Thread(target=self._import_ytdlp, daemon=True).start()

    def _import_ytdlp(self):
        global yt_dlp
        import yt_dlp as _yt
        yt_dlp = _yt
        self._ytdlp_ready = True
        self._on_ytdlp_ready()

    @mainthread
    def _on_ytdlp_ready(self):
        self.check_btn.disabled = False
        self.check_btn.background_color = hex_color(C_PRIMARY)
        self.set_status("Ready — paste a URL and tap Check", color=C_SUCCESS)

    def request_android_permissions(self):
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
            ])
        except Exception:
            pass

    @mainthread
    def set_status(self, text, color=C_SUBTEXT):
        self.status_label.text = text
        self.status_label.color = hex_color(color)

    @mainthread
    def set_progress(self, value):
        self.progress.value = value

    @mainthread
    def populate_qualities(self, options):
        self.quality_spinner.values = options
        if options:
            self.quality_spinner.text = options[0]
            self.quality_spinner.disabled = False
            self.download_btn.disabled = False
            self.download_btn.background_color = hex_color(C_SUCCESS)
        self.check_btn.disabled = False
        self.check_btn.background_color = hex_color(C_PRIMARY)

    # ---------- Check ----------

    def check_formats(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Please enter a URL", color=C_DANGER)
            return
        self.check_btn.disabled = True
        self.check_btn.background_color = hex_color(C_PRIMARY, 0.4)
        self.set_status("Checking available qualities...", color=C_SUBTEXT)
        threading.Thread(target=self._check_formats_thread, args=(url,), daemon=True).start()

    def _check_formats_thread(self, url):
        try:
            ydl_opts = {
                "quiet": True, "no_warnings": True,
                "logger": _QuietLogger(), "skip_download": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            heights = set()
            for f in info.get("formats", []):
                h = f.get("height")
                if h and f.get("vcodec") != "none" and f.get("acodec") != "none":
                    heights.add(h)

            options = [f"{h}p" for h in sorted(heights, reverse=True)]
            options.append("Audio Only")
            self.populate_qualities(options)
            self.set_status("Select quality then tap Download ✓", color=C_SUCCESS)
        except Exception as e:
            self.set_status(f"Error: {str(e)[:120]}", color=C_DANGER)
            self.check_btn.disabled = False
            self.check_btn.background_color = hex_color(C_PRIMARY)

    # ---------- Download ----------

    def download_video(self, instance):
        url = self.url_input.text.strip()
        quality = self.quality_spinner.text
        if not url or quality == "Select Quality":
            self.set_status("Please select a URL and quality first", color=C_DANGER)
            return
        self.download_btn.disabled = True
        self.download_btn.background_color = hex_color(C_SUCCESS, 0.4)
        self.set_status("Starting download...", color=C_SUBTEXT)
        self.set_progress(0)
        threading.Thread(target=self._download_thread, args=(url, quality), daemon=True).start()

    def _progress_hook(self, d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = downloaded / total * 100
                self.set_progress(pct)
                self.set_status(f"Downloading... {pct:.0f}%", color=C_SUBTEXT)
        elif d.get("status") == "finished":
            self.set_status("Saving file...", color=C_SUBTEXT)

    def _download_thread(self, url, quality):
        output_dir = get_download_dir()
        tmpl = os.path.join(output_dir, "%(title).80s.%(ext)s")
        base_opts = {
            "outtmpl": tmpl, "quiet": True,
            "no_warnings": True, "logger": _QuietLogger(),
            "progress_hooks": [self._progress_hook],
        }
        if quality == "Audio Only":
            base_opts["format"] = "bestaudio/best"
        else:
            h = quality.replace("p", "")
            base_opts["format"] = (
                f"best[height<={h}][vcodec!=none][acodec!=none]/best[height<={h}]"
            )
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                ydl.extract_info(url, download=True)
            self.set_progress(100)
            self.set_status("Downloaded successfully! ✓", color=C_SUCCESS)
        except Exception as e:
            self.set_status(f"Failed: {str(e)[:120]}", color=C_DANGER)
        finally:
            self.download_btn.disabled = False
            self.download_btn.background_color = hex_color(C_SUCCESS)


if __name__ == "__main__":
    DownloaderApp().run()
