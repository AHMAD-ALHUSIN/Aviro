package org.myapp;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import java.io.File;
import java.nio.ByteBuffer;

public class MediaMerger {

    public String mergeBlocking(final Context context, final String videoPath, final String audioPath, final String outputPath) {
        MediaExtractor videoExtractor = null;
        MediaExtractor audioExtractor = null;
        MediaMuxer muxer = null;

        try {
            File outFile = new File(outputPath);
            if (outFile.getParentFile() != null && !outFile.getParentFile().exists()) {
                outFile.getParentFile().mkdirs();
            }
            if (outFile.exists()) {
                outFile.delete();
            }

            // 1. إعداد استخراج مسار الفيديو
            videoExtractor = new MediaExtractor();
            videoExtractor.setDataSource(videoPath);
            int videoTrackIndex = -1;
            MediaFormat videoFormat = null;

            for (int i = 0; i < videoExtractor.getTrackCount(); i++) {
                MediaFormat format = videoExtractor.getTrackFormat(i);
                String mime = format.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("video/")) {
                    videoTrackIndex = i;
                    videoFormat = format;
                    break;
                }
            }

            if (videoTrackIndex == -1) {
                return "Error: No video track found in " + videoPath;
            }

            // 2. إعداد استخراج مسار الصوت
            audioExtractor = new MediaExtractor();
            audioExtractor.setDataSource(audioPath);
            int audioTrackIndex = -1;
            MediaFormat audioFormat = null;

            for (int i = 0; i < audioExtractor.getTrackCount(); i++) {
                MediaFormat format = audioExtractor.getTrackFormat(i);
                String mime = format.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    audioTrackIndex = i;
                    audioFormat = format;
                    break;
                }
            }

            if (audioTrackIndex == -1) {
                return "Error: No audio track found in " + audioPath;
            }

            // 3. إنشاء المدمج (Muxer) بفتحات الصوت والفيديو
            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            
            videoExtractor.selectTrack(videoTrackIndex);
            int muxerVideoTrack = muxer.addTrack(videoFormat);

            audioExtractor.selectTrack(audioTrackIndex);
            int muxerAudioTrack = muxer.addTrack(audioFormat);

            muxer.start();

            // 4. نسخ بيانات الفيديو مباشرة بدون إعادة تشفير (Direct Buffer Copy)
            ByteBuffer buffer = ByteBuffer.allocate(2 * 1024 * 1024); // ذاكرة مؤقتة بحجم 2MB
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            while (true) {
                bufferInfo.offset = 0;
                bufferInfo.size = videoExtractor.readSampleData(buffer, 0);
                if (bufferInfo.size < 0) {
                    break;
                }
                bufferInfo.presentationTimeUs = videoExtractor.getSampleTime();
                bufferInfo.flags = videoExtractor.getSampleFlags();
                muxer.writeSampleData(muxerVideoTrack, buffer, bufferInfo);
                videoExtractor.advance();
            }

            // 5. نسخ بيانات الصوت مباشرة
            while (true) {
                bufferInfo.offset = 0;
                bufferInfo.size = audioExtractor.readSampleData(buffer, 0);
                if (bufferInfo.size < 0) {
                    break;
                }
                bufferInfo.presentationTimeUs = audioExtractor.getSampleTime();
                bufferInfo.flags = audioExtractor.getSampleFlags();
                muxer.writeSampleData(muxerAudioTrack, buffer, bufferInfo);
                audioExtractor.advance();
            }

            return "SUCCESS";

        } catch (Exception e) {
            return "Exception: " + e.getMessage();
        } finally {
            // إغلاق الموارد وحفظ الملف
            try {
                if (videoExtractor != null) videoExtractor.release();
                if (audioExtractor != null) audioExtractor.release();
                if (muxer != null) {
                    try {
                        muxer.stop();
                    } catch (Exception ignored) {}
                    muxer.release();
                }
            } catch (Exception ignored) {}
        }
    }
}
