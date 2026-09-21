import flet as ft
import yt_dlp
import os

def main(page: ft.Page):
    page.title = "مُحمّل الفيديوهات"
    page.theme_mode = ft.ThemeMode.DARK
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    url_input = ft.TextField(label="أدخل رابط الفيديو هنا...", width=350)
    status_text = ft.Text(value="", color=ft.colors.BLUE)

    def download_click(e):
        if not url_input.value:
            status_text.value = "❌ يرجى إدخال الرابط!"
            status_text.color = ft.colors.RED
            page.update()
            return

        status_text.value = "⏳ جاري التحميل..."
        status_text.color = ft.colors.ORANGE
        page.update()

        try:
            ydl_opts = {
                'outtmpl': '/sdcard/Download/%(title)s.%(ext)s',
                'format': 'best',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url_input.value])
            status_text.value = "✅ تم التحميل في مجلد التنزيلات!"
            status_text.color = ft.colors.GREEN
        except Exception as err:
            status_text.value = f"❌ حدث خطأ: {str(err)[:50]}"
            status_text.color = ft.colors.RED
        
        page.update()

    download_btn = ft.ElevatedButton("بدء التحميل 🚀", on_click=download_click)

    page.add(
        ft.Text("مُحمّل الفيديوهات الشامل", size=22, weight=ft.FontWeight.BOLD),
        url_input,
        download_btn,
        status_text
    )

ft.app(target=main)
