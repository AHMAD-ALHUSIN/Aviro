package org.myapp;

import android.content.Context;
import android.net.Uri;
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
    
    // هذه الدالة سيتم استدعاؤها من بايثون باستخدام PyJnius
    public String mergeBlocking(Context context, String videoPath, String audioPath, String outputPath) {
        CountDownLatch latch = new CountDownLatch(1);
        final String[] resultMsg = new String[1];

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
                        resultMsg[0] = "Error: " + exportException.getMessage();
                        latch.countDown();
                    }
                })
                .build();

            transformer.start(composition, outputPath);
            
            // انتظار انتهاء الدمج
            latch.await();
            
        } catch (Exception e) {
            resultMsg[0] = "Exception: " + e.getMessage();
        }
        
        return resultMsg[0];
    }
}
