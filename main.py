import os
import sys
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.utils import platform
import yt_dlp

class YTDownloaderApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        self.url_input = TextInput(
            hint_text='أدخل رابط الفيديو هنا...',
            size_hint=(1, 0.15),
            multiline=False
        )
        self.download_btn = Button(
            text='تحميل بأعلى جودة (1080p+) ودمج الصوت',
            size_hint=(1, 0.15),
            background_color=(0.2, 0.6, 1, 1)
        )
        self.download_btn.bind(on_press=self.start_download)
        
        self.status_label = Label(
            text='التطبيق جاهز للتحميل',
            size_hint=(1, 0.7),
            halign='center',
            valign='middle'
        )
        self.status_label.bind(size=self.status_label.setter('text_size'))

        self.layout.add_widget(self.url_input)
        self.layout.add_widget(self.download_btn)
        self.layout.add_widget(self.status_label)

        self.request_permissions()
        return self.layout

    def request_permissions(self):
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE
            ])

    def get_ffmpeg_path(self):
        """تحديد مسار ffmpeg المدمج مع التطبيق وإعطائه صلاحية التشغيل"""
        if platform == 'android':
            app_dir = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_bin = os.path.join(app_dir, 'ffmpeg')
            if os.path.exists(ffmpeg_bin):
                try:
                    os.chmod(ffmpeg_bin, 0o755)
                except Exception as e:
                    print(f"Error setting executable permission: {e}")
                return ffmpeg_bin
        return 'ffmpeg'

    def start_download(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.status_label.text = "يرجى إدخال الرابط أولاً!"
            return

        self.status_label.text = "جاري تحميل أفضل فيديو وصوت ودمجهما...\nقد يستغرق ذلك بعض الوقت حسب طول الفيديو."
        self.download_btn.disabled = True
        
        threading.Thread(target=self.download_video, args=(url,), daemon=True).start()

    def download_video(self, url):
        try:
            if platform == 'android':
                save_path = '/storage/emulated/0/Download/%(title)s.%(ext)s'
            else:
                save_path = '%(title)s.%(ext)s'

            ffmpeg_location = self.get_ffmpeg_path()

            # إعدادات yt-dlp للتحميل بأعلى جودة + الدمج
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'outtmpl': save_path,
                'ffmpeg_location': ffmpeg_location,
                'quiet': True,
                'no_warnings': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            Clock.schedule_once(lambda dt: self.update_status("تم التحميل والدمج بنجاح!\nتجد الفيديو المدمج في مجلد (Download)"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"حدث خطأ أثناء التحميل أو الدمج:\n{str(e)}"))

    def update_status(self, text):
        self.status_label.text = text
        self.download_btn.disabled = False

if __name__ == '__main__':
    YTDownloaderApp().run()
