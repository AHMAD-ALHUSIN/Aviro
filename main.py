import flet as ft
import yt_dlp
import os

def main(page: ft.Page):
    page.title = "مُحمّل الفيديوهات الذكي"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # حقل إدخال الرابط
    url_input = ft.TextField(
        label="أدخل رابط الفيديو",
        width=380,
        autofocus=True
    )

    # قائمة اختيار الجودة والصوت
    quality_dropdown = ft.Dropdown(
        width=380,
        label="اختر الجودة المطلوبة",
        value="best",
        options=[
            ft.dropdown.Option("best", "🚀 أعلى جودة فيديو متوفرة"),
            ft.dropdown.Option("1080", "🎬 جودة عالية (1080p)"),
            ft.dropdown.Option("720", "📺 جودة متوسطة (720p)"),
            ft.dropdown.Option("480", "📱 جودة منخفضة (480p)"),
            ft.dropdown.Option("audio", "🎵 صوت فقط (أعلى جودة صوت متوفرة Best Audio)"),
        ],
    )

    status_text = ft.Text("", size=14)

    def download_click(e):
        url = url_input.value.strip() if url_input.value else ""
        if not url:
            status_text.value = "❌ يرجى إدخال الرابط أولاً!"
            status_text.color = "red"
            page.update()
            return
        
        status_text.value = "⏳ جاري التحميل... يرجى الانتظار"
        status_text.color = "orange"
        page.update()

        # إعداد مسار الحفظ (أندرويد أو كمبيوتر)
        if os.path.exists("/sdcard/Download"):
            download_folder = "/sdcard/Download"
        else:
            download_folder = os.path.join(os.path.expanduser('~'), 'Downloads')

        selected_option = quality_dropdown.value

        # تحديد أسلوب التحميل والجودة
        if selected_option == "audio":
            # اختيار أعلى دقة ونقاء للصوت فقط بدون فيديو
            format_option = 'bestaudio/best'
        elif selected_option == "1080":
            format_option = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
        elif selected_option == "720":
            format_option = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
        elif selected_option == "480":
            format_option = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
        else: # best
            format_option = 'bestvideo+bestaudio/best'

        ydl_opts = {
            'outtmpl': os.path.join(download_folder, '%(title)s.%(ext)s'),
            'format': format_option,
            'noplaylist': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            status_text.value = "✅ تم تحميل الصوت بأعلى جودة بنجاح!" if selected_option == "audio" else "✅ تم التحميل بنجاح!"
            status_text.color = "green"
            url_input.value = ""
        except Exception as err:
            status_text.value = "❌ حدث خطأ أثناء التحميل"
            status_text.color = "red"
        
        page.update()

    download_button = ft.Button(
        content=ft.Text("بدء التحميل 🚀"),
        on_click=download_click,
        width=220
    )

    page.add(
        ft.Text("مُحمّل الفيديوهات والصوتيات", size=24, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        url_input,
        quality_dropdown,
        download_button,
        status_text
    )

if __name__ == "__main__":
    ft.run(main)
