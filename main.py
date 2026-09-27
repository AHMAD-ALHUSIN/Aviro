def fetch_formats_thread(self, url):
        try:
            ydl_opts = {
                'quiet': True, 'no_warnings': True, 'logger': YTDLogger(), 'nocheckcertificate': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])

                options = {}
                
                # استخراج أفضل مسار صوتي منفصل
                audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
                best_audio_id = audio_formats[-1]['format_id'] if audio_formats else None

                # استخراج مسارات الفيديو وتجميعها حسب الدقة
                for f in formats:
                    vcodec = f.get('vcodec')
                    acodec = f.get('acodec')
                    format_id = f.get('format_id')
                    height = f.get('height')

                    if vcodec != 'none':
                        if height:
                            label = f"{height}p"
                            # إذا كان الملف يحتوي على صوت وفيديو جاهز، نمرر None للصوت
                            if acodec != 'none':
                                options[f"{label} (Ready)"] = (format_id, None)
                            # إذا كان فيديو فقط، نربطه بأفضل مسار صوتي
                            elif best_audio_id:
                                options[label] = (format_id, best_audio_id)

                def _update_spinner(dt):
                    self.format_map = options
                    self.quality_spinner.values = list(options.keys())
                    if self.quality_spinner.values:
                        self.quality_spinner.text = self.quality_spinner.values[-1] # اختيار أعلى جودة افتراضياً
                    self.set_status('Qualities loaded. Select format and tap Download.')
                    self.fetch_btn.disabled = False
                    self.download_btn.disabled = False

                Clock.schedule_once(_update_spinner)

        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self.set_status(f'Error:\n{err}'))
            Clock.schedule_once(lambda dt: setattr(self.fetch_btn, 'disabled', False))

    def download_video(self, url, format_tuple):
        try:
            video_id, audio_id = format_tuple
            save_dir = self.get_save_directory()
            
            # استخراج عنوان الفيديو أولاً لتسمية الملف النهائي
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                safe_title = info.get('title', 'Video').replace('/', '_').replace('\\', '_')
            
            final_path = os.path.join(save_dir, f"{safe_title}.mp4")

            # الحالة الأولى: الملف يحتوي مسبقاً على صوت وفيديو (لا يحتاج دمج)
            if audio_id is None:
                self.set_status('Downloading...')
                ydl_opts = {
                    'format': video_id,
                    'outtmpl': final_path,
                    'progress_hooks': [self.progress_hook],
                    'quiet': True, 'logger': YTDLogger()
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                self.scan_file_to_gallery(final_path)
                Clock.schedule_once(lambda dt: self.finish_success())
                return

            # الحالة الثانية: دمج فيديو وصوت باستخدام Media3
            if platform == 'android':
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                cache_dir = PythonActivity.mActivity.getExternalCacheDir().getAbsolutePath()
            else:
                cache_dir = os.getcwd() # للتجارب على الكمبيوتر (سيفشل الدمج بدون Android)

            video_tmp = os.path.join(cache_dir, "video.tmp")
            audio_tmp = os.path.join(cache_dir, "audio.tmp")

            # حذف الملفات المؤقتة القديمة إن وجدت
            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp): os.remove(tmp)

            # تنزيل الفيديو
            Clock.schedule_once(lambda dt: self.set_status('Downloading Video...'))
            with yt_dlp.YoutubeDL({'format': video_id, 'outtmpl': video_tmp, 'quiet': True, 'logger': YTDLogger()}) as ydl:
                ydl.download([url])

            # تنزيل الصوت
            Clock.schedule_once(lambda dt: self.set_status('Downloading Audio...'))
            with yt_dlp.YoutubeDL({'format': audio_id, 'outtmpl': audio_tmp, 'quiet': True, 'logger': YTDLogger()}) as ydl:
                ydl.download([url])

            # عملية الدمج
            Clock.schedule_once(lambda dt: self.set_status('Merging with Media3... (Please wait)'))
            
            if platform == 'android':
                MediaMerger = autoclass('org.myapp.MediaMerger')
                merger = MediaMerger()
                result = merger.mergeBlocking(PythonActivity.mActivity, video_tmp, audio_tmp, final_path)
                
                if result == "SUCCESS":
                    self.scan_file_to_gallery(final_path)
                    Clock.schedule_once(lambda dt: self.finish_success())
                else:
                    Clock.schedule_once(lambda dt: self.finish_error(f'Merge Error: {result}'))
            
            # تنظيف الملفات المؤقتة
            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp): os.remove(tmp)

        except Exception as e:
            Clock.schedule_once(lambda dt: self.finish_error(str(e)))
