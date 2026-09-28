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

            // 1. إعداد مسار الفيديو
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

            // 2. إعداد مسار الصوت
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

            // 3. إنشاء المدمج (Muxer)
            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            videoExtractor.selectTrack(videoTrackIndex);
            int muxerVideoTrack = muxer.addTrack(videoFormat);

            audioExtractor.selectTrack(audioTrackIndex);
            int muxerAudioTrack = muxer.addTrack(audioFormat);

            muxer.start();

            // 🌟 تحسين 1: حساب الحجم الأقصى للـ Buffer ديناميكياً بدلاً من تثبيته
            int maxBufferSize = 256 * 1024; // قيمة مبدئية
            if (videoFormat.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                maxBufferSize = Math.max(maxBufferSize, videoFormat.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE));
            }
            if (audioFormat.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                maxBufferSize = Math.max(maxBufferSize, audioFormat.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE));
            }

            // تخصيص الذاكرة بناءً على أكبر إطار متوقع
            ByteBuffer buffer = ByteBuffer.allocateDirect(maxBufferSize);
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();

            // 5. الدمج المتداخل زمنيًا (Interleaving)
            boolean hasVideo = true;
            boolean hasAudio = true;

            while (hasVideo || hasAudio) {
                long videoTime = hasVideo ? videoExtractor.getSampleTime() : -1;
                if (videoTime < 0) hasVideo = false;

                long audioTime = hasAudio ? audioExtractor.getSampleTime() : -1;
                if (audioTime < 0) hasAudio = false;

                if (!hasVideo && !hasAudio) break;

                boolean writeVideo;
                if (hasVideo && hasAudio) {
                    writeVideo = (videoTime <= audioTime);
                } else {
                    writeVideo = hasVideo;
                }

                // 🌟 تحسين 2: تصفير الـ Buffer قبل كل قراءة لتجنب تداخل البيانات
                buffer.clear(); 

                if (writeVideo) {
                    bufferInfo.offset = 0;
                    bufferInfo.size = videoExtractor.readSampleData(buffer, 0);
                    if (bufferInfo.size < 0) {
                        hasVideo = false;
                    } else {
                        bufferInfo.presentationTimeUs = videoTime;
                        bufferInfo.flags = videoExtractor.getSampleFlags();
                        muxer.writeSampleData(muxerVideoTrack, buffer, bufferInfo);
                        videoExtractor.advance();
                    }
                } else {
                    bufferInfo.offset = 0;
                    bufferInfo.size = audioExtractor.readSampleData(buffer, 0);
                    if (bufferInfo.size < 0) {
                        hasAudio = false;
                    } else {
                        bufferInfo.presentationTimeUs = audioTime;
                        bufferInfo.flags = audioExtractor.getSampleFlags();
                        muxer.writeSampleData(muxerAudioTrack, buffer, bufferInfo);
                        audioExtractor.advance();
                    }
                }
            }

            return "SUCCESS";

        } catch (Exception e) {
            return "Exception: " + e.getMessage();
        } finally {
            // إغلاق الموارد بشكل آمن
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
