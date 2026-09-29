package org.ahmad.aviro;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.os.Build;

import java.io.File;
import java.nio.ByteBuffer;

public class MediaMerger {

    private static final int INITIAL_BUFFER_SIZE = 2 * 1024 * 1024; // 2MB (يكفي لمعظم إطارات 4K)
    private static final int PROGRESS_EVERY_N_SAMPLES = 64;

    private volatile boolean cancelled = false;
    private volatile int progress = 0;

    /** يُستدعى من بايثون لإلغاء الدمج الجاري. */
    public void cancel() {
        cancelled = true;
    }

    /** نسبة تقدم الدمج 0..100 (يُستدعى من بايثون بشكل دوري). */
    public int getProgress() {
        return progress;
    }

    public String mergeBlocking(final Context context, final String videoPath,
                                final String audioPath, final String outputPath) {
        cancelled = false;
        progress = 0;

        MediaExtractor videoExtractor = null;
        MediaExtractor audioExtractor = null;
        MediaMuxer muxer = null;
        boolean muxerStarted = false;
        boolean muxerStopped = false;
        boolean success = false;

        try {
            File outFile = new File(outputPath);
            File parent = outFile.getParentFile();
            if (parent != null && !parent.exists()) {
                parent.mkdirs();
            }
            if (outFile.exists()) {
                outFile.delete();
            }

            // 1. مسار الفيديو
            videoExtractor = new MediaExtractor();
            videoExtractor.setDataSource(videoPath);
            int videoTrackIndex = findTrack(videoExtractor, "video/");
            if (videoTrackIndex < 0) {
                return "Error: No video track found in " + videoPath;
            }
            MediaFormat videoFormat = videoExtractor.getTrackFormat(videoTrackIndex);

            // 2. مسار الصوت
            audioExtractor = new MediaExtractor();
            audioExtractor.setDataSource(audioPath);
            int audioTrackIndex = findTrack(audioExtractor, "audio/");
            if (audioTrackIndex < 0) {
                return "Error: No audio track found in " + audioPath;
            }
            MediaFormat audioFormat = audioExtractor.getTrackFormat(audioTrackIndex);

            // 3. إنشاء الـ Muxer
            muxer = new MediaMuxer(outputPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);

            // الحفاظ على دوران الفيديو (مقاطع الموبايل العمودية)
            if (Build.VERSION.SDK_INT >= 23 && videoFormat.containsKey(MediaFormat.KEY_ROTATION)) {
                try {
                    muxer.setOrientationHint(videoFormat.getInteger(MediaFormat.KEY_ROTATION));
                } catch (Exception ignored) {
                }
            }

            int muxerVideoTrack;
            int muxerAudioTrack;
            try {
                muxerVideoTrack = muxer.addTrack(videoFormat);
                muxerAudioTrack = muxer.addTrack(audioFormat);
            } catch (IllegalArgumentException | IllegalStateException e) {
                return "Unsupported codec for MP4 on this device: video="
                        + videoFormat.getString(MediaFormat.KEY_MIME)
                        + ", audio=" + audioFormat.getString(MediaFormat.KEY_MIME)
                        + " (" + e + ")";
            }

            videoExtractor.selectTrack(videoTrackIndex);
            audioExtractor.selectTrack(audioTrackIndex);

            long duration = Math.max(getDuration(videoFormat), getDuration(audioFormat));

            muxer.start();
            muxerStarted = true;

            // 4. حجم الـ Buffer: ابدأ بقيمة مناسبة ثم كبّره تلقائياً عند الحاجة
            int bufferSize = INITIAL_BUFFER_SIZE;
            bufferSize = Math.max(bufferSize, getIntSafe(videoFormat, MediaFormat.KEY_MAX_INPUT_SIZE));
            bufferSize = Math.max(bufferSize, getIntSafe(audioFormat, MediaFormat.KEY_MAX_INPUT_SIZE));
            ByteBuffer buffer = ByteBuffer.allocateDirect(bufferSize);
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();

            // 5. دمج متداخل زمنياً (Interleaving) مع تخزين أوقات العيّنات لتقليل استدعاءات JNI
            long videoTime = videoExtractor.getSampleTime();
            long audioTime = audioExtractor.getSampleTime();
            int counter = 0;

            while (videoTime >= 0 || audioTime >= 0) {
                if (cancelled) {
                    return "CANCELLED";
                }

                boolean writeVideo = videoTime >= 0 && (audioTime < 0 || videoTime <= audioTime);
                MediaExtractor extractor = writeVideo ? videoExtractor : audioExtractor;
                int track = writeVideo ? muxerVideoTrack : muxerAudioTrack;
                long sampleTime = writeVideo ? videoTime : audioTime;

                // تكبير الـ Buffer إذا كانت العيّنة الحالية أكبر منه
                long sampleSize = extractor.getSampleSize();
                if (sampleSize > buffer.capacity()) {
                    int newSize = (int) Math.max(sampleSize + 65536L, (long) buffer.capacity() * 2L);
                    buffer = ByteBuffer.allocateDirect(newSize);
                }

                buffer.clear();
                int size = extractor.readSampleData(buffer, 0);
                if (size < 0) {
                    if (writeVideo) videoTime = -1; else audioTime = -1;
                    continue;
                }

                int extractorFlags = extractor.getSampleFlags();
                int flags = (extractorFlags & MediaExtractor.SAMPLE_FLAG_SYNC) != 0
                        ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0;

                info.set(0, size, sampleTime, flags);
                muxer.writeSampleData(track, buffer, info);

                extractor.advance();
                long next = extractor.getSampleTime();
                if (writeVideo) videoTime = next; else audioTime = next;

                if (duration > 0 && (++counter % PROGRESS_EVERY_N_SAMPLES) == 0) {
                    int p = (int) Math.min(99L, sampleTime * 100L / duration);
                    if (p > progress) progress = p;
                }
            }

            // 6. إنهاء الملف: أي فشل هنا يُعاد كخطأ حقيقي (وليس SUCCESS)
            try {
                muxer.stop();
                muxerStopped = true;
            } catch (Exception e) {
                return "Muxer stop failed: " + e;
            }

            progress = 100;
            success = true;
            return "SUCCESS";

        } catch (Throwable t) {
            return "Exception: " + t;
        } finally {
            try {
                if (videoExtractor != null) videoExtractor.release();
            } catch (Exception ignored) {
            }
            try {
                if (audioExtractor != null) audioExtractor.release();
            } catch (Exception ignored) {
            }
            if (muxer != null) {
                if (muxerStarted && !muxerStopped) {
                    try {
                        muxer.stop();
                    } catch (Exception ignored) {
                    }
                }
                try {
                    muxer.release();
                } catch (Exception ignored) {
                }
            }
            if (!success) {
                try {
                    new File(outputPath).delete();
                } catch (Exception ignored) {
                }
            }
        }
    }

    private static int findTrack(MediaExtractor extractor, String mimePrefix) {
        for (int i = 0; i < extractor.getTrackCount(); i++) {
            String mime = extractor.getTrackFormat(i).getString(MediaFormat.KEY_MIME);
            if (mime != null && mime.startsWith(mimePrefix)) {
                return i;
            }
        }
        return -1;
    }

    private static long getDuration(MediaFormat format) {
        try {
            if (format.containsKey(MediaFormat.KEY_DURATION)) {
                return format.getLong(MediaFormat.KEY_DURATION);
            }
        } catch (Exception ignored) {
        }
        return 0L;
    }

    private static int getIntSafe(MediaFormat format, String key) {
        try {
            if (format.containsKey(key)) {
                return format.getInteger(key);
            }
        } catch (Exception ignored) {
        }
        return 0;
    }
}
