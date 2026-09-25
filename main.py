import os
import threading

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.clock import mainthread
from kivy.utils import platform

import yt_dlp


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
        self.title = "محمل الفيديوهات"
        root = BoxLayout(orientation="vertical", padding=20, spacing=12)

        self.url_input = TextInput(
            hint_text="الصق رابط الفيديو هنا",
            size_hint_y=None,
            height=50,
            multiline=False,
        )
        root.add_widget(self.url_input)

        self.check_btn = Button(text="فحص الجودات المتوفرة", size_hint_y=None, height=55)
        self.check_btn.bind(on_release=self.check_formats)
        root.add_widget(self.check_btn)

        self.quality_spinner = Spinner(
            text="اختر الجودة",
            values=[],
            size_hint_y=None,
            height=50,
            disabled=True,
        )
        root.add_widget(self.quality_spinner)

        self.download_btn = Button(text="تحميل", size_hint_y=None, height=55, disabled=True)
        self.download_btn.bind(on_release=self.download_video)
        root.add_widget(self.download_btn)

        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=20)
        root.add_widget(self.progress)

        self.status_label = Label(text="", size_hint_y=None, height=100)
        root.add_widget(self.status_label)

        root.add_widget(BoxLayout())  # spacer

        if platform == "android":
            self.request_android_permissions()

        return root

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
    def set_status(self, text):
        self.status_label.text = text

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
        self.check_btn.disabled = False

    # ---------- فحص الجودات ----------

    def check_formats(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.set_status("الرجاء إدخال رابط")
            return
        self.check_btn.disabled = True
        self.set_status("جاري الفحص...")
        threading.Thread(target=self._check_formats_thread, args=(url,), daemon=True).start()

    def _check_formats_thread(self, url):
        try:
            ydl_opts = {"quiet": True, "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = info.get("formats", [])
            heights = set()
            for f in formats:
                h = f.get("height")
                # نختار فقط الصيغ التي تحتوي فيديو + صوت معًا (بدون الحاجة لدمج بـ ffmpeg)
                if h and f.get("vcodec") != "none" and f.get("acodec") != "none":
                    heights.add(h)

            sorted_heights = sorted(heights, reverse=True)
            options = [f"{h}p" for h in sorted_heights]
            options.append("صوت فقط")

            if not sorted_heights:
                self.set_status("لا توجد جودات فيديو+صوت مدمجة لهذا الفيديو")

            self.populate_qualities(options)
            self.set_status("اختر الجودة ثم اضغط تحميل")
        except Exception as e:
            self.set_status(f"خطأ: {str(e)[:150]}")
            self.check_btn.disabled = False

    # ---------- التحميل ----------

    def download_video(self, instance):
        url = self.url_input.text.strip()
        quality = self.quality_spinner.text
        if not url or quality == "اختر الجودة":
            self.set_status("اختر رابط وجودة أولاً")
            return
        self.download_btn.disabled = True
        self.set_status("جاري التحميل...")
        self.set_progress(0)
        threading.Thread(target=self._download_thread, args=(url, quality), daemon=True).start()

    def _progress_hook(self, d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                percent = downloaded / total * 100
                self.set_progress(percent)
                self.set_status(f"جاري التحميل... {percent:.0f}%")
        elif d.get("status") == "finished":
            self.set_status("اكتمل التحميل، جاري الحفظ...")

    def _download_thread(self, url, quality):
        output_dir = get_download_dir()
        output_template = os.path.join(output_dir, "%(title).80s.%(ext)s")

        if quality == "صوت فقط":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "progress_hooks": [self._progress_hook],
            }
        else:
            height = quality.replace("p", "")
            ydl_opts = {
                "format": f"best[height<={height}][vcodec!=none][acodec!=none]/best[height<={height}]",
                "outtmpl": output_template,
                "quiet": True,
                "progress_hooks": [self._progress_hook],
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            self.set_progress(100)
            self.set_status(f"تم التحميل بنجاح إلى:\n{output_dir}")
        except Exception as e:
            self.set_status(f"فشل التحميل: {str(e)[:150]}")
        finally:
            self.download_btn.disabled = False


if __name__ == "__main__":
    DownloaderApp().run()
