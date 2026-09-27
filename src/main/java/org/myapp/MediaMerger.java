package org.myapp;

import android.content.Context;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import androidx.media3.common.MediaItem;
import androidx.media3.transformer.Composition;
import androidx.media3.transformer.EditedMediaItem;
import androidx.media3.transformer.EditedMediaItemSequence;
import androidx.media3.transformer.ExportException;
import androidx.media3.transformer.ExportResult;
import androidx.media3.transformer.Transformer;
import java.io.File;
import java.util.concurrent.CountDownLatch;

public class MediaMerger {

    public String mergeBlocking(final Context context, final String videoPath, final String audioPath, final String outputPath) {
        final CountDownLatch latch = new CountDownLatch(1);
        final String[] resultMsg = new String[]{"UNKNOWN_ERROR"};

        try {
            File outFile = new File(outputPath);
            if (outFile.getParentFile() != null && !outFile.getParentFile().exists()) {
                outFile.getParentFile().mkdirs();
            }

            // تشغيل Transformer داخل Main Looper لمنع توقف التطبيق
            Handler mainHandler = new Handler(Looper.getMainLooper());
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    try {
                        EditedMediaItem videoItem = new EditedMediaItem.Builder(MediaItem.fromUri(Uri.fromFile(new File(videoPath)))).build();
                        EditedMediaItem audioItem = new EditedMediaItem.Builder(MediaItem.fromUri(Uri.fromFile(new File(audioPath)))).build();

                        EditedMediaItemSequence videoSeq = new EditedMediaItemSequence(videoItem);
                        EditedMediaItemSequence audioSeq = new EditedMediaItemSequence(audioItem);

                        Composition composition = new Composition.Builder(videoSeq, audioSeq).build();

                        Transformer transformer = new Transformer.Builder(context)
                            .addListener(new Transformer.Listener() {
                                @Override
                                public void onCompleted(Composition composition, ExportResult exportResult) {
                                    resultMsg[0] = "SUCCESS";
                                    latch.countDown();
                                }

                                @Override
                                public void onError(Composition composition, ExportResult exportResult, ExportException exportException) {
                                    resultMsg[0] = "Error: " + (exportException != null ? exportException.getMessage() : "Export failed");
                                    latch.countDown();
                                }
                            })
                            .build();

                        transformer.start(composition, outputPath);
                    } catch (Exception e) {
                        resultMsg[0] = "Exception on UI thread: " + e.getMessage();
                        latch.countDown();
                    }
                }
            });

            latch.await();

        } catch (Exception e) {
            resultMsg[0] = "Exception: " + e.getMessage();
        }

        return resultMsg[0];
    }
}
