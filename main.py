import os
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
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        self.url_input = TextInput(hint_text='أدخل رابط الفيديو هنا...', size_hint=(1, 0.2))
        self.download_btn = Button(text='تحميل الفيديو', size_hint=(1, 0.2))
        self.download_btn.bind(on_press=self.start_download)
        self.status_label = Label(text='التطبيق جاهز', size_hint=(1, 0.6), halign='center')

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

    def start_download(self, instance):
        url = self.url_input.text.strip()
        if not url:
            self.status_label.text = "يرجى إدخال الرابط أولاً!"
            return

        self.status_label.text = "جاري التحميل ودمج الصوت بالفيديو... يرجى الانتظار"
        self.download_btn.disabled = True
        
        threading.Thread(target=self.download_video, args=(url,)).start()

    def download_video(self, url):
        try:
            if platform == 'android':
                save_path = '/storage/emulated/0/Download/%(title)s.%(ext)s'
            else:
                save_path = '%(title)s.%(ext)s'

            # تحديد مسار ffmpeg المباشر الموجود بجانب main.py
            app_dir = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_path = os.path.join(app_dir, 'ffmpeg')

            # إعطاء صلاحية التشغيل لملف ffmpeg
            if os.path.exists(ffmpeg_path):
                try:
                    os.chmod(ffmpeg_path, 0o755)
                except Exception:
                    pass

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': save_path,
                'quiet': True,
                'no_warnings': True,
            }

            # إسناد المسار لـ yt-dlp
            if os.path.exists(ffmpeg_path):
                ydl_opts['ffmpeg_location'] = ffmpeg_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            Clock.schedule_once(lambda dt: self.update_status("تم التحميل ودمج الصوت مع الفيديو بنجاح!\nتجد الملف في مجلد التنزيلات (Download)"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"حدث خطأ أثناء التحميل:\n{str(e)}"))

    def update_status(self, text):
        self.status_label.text = text
        self.download_btn.disabled = False

if __name__ == '__main__':
    YTDownloaderApp().run()
