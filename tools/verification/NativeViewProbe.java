package local.zy.boardprobe;

import android.content.Context;
import android.graphics.Bitmap;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.util.List;

/** Exercise the vendor's View entry points with an ordinary touch sequence on the UI thread. */
final class NativeViewProbe {
    static void run(Context context, ClassLoader loader, File dir) throws Exception {
        Class<?> type = loader.loadClass("com.zykj.view.simpleBoard.SimpleBoardView");
        View view = (View)type.getConstructor(Context.class).newInstance(context);
        int w = 320, h = 240;
        view.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY),
                     View.MeasureSpec.makeMeasureSpec(h, View.MeasureSpec.EXACTLY));
        view.layout(0, 0, w, h);
        type.getMethod("loadStrokeData", String.class).invoke(view, new File(dir,"simple").getPath());
        Bitmap picture = (Bitmap)type.getMethod("buildBitmap").invoke(view);
        int painted = 0;
        for (int y=0;y<h;y++) for (int x=0;x<w;x++)
            if ((picture.getPixel(x,y)&0x00ffffff) != 0x00ffffff) painted++;
        if (painted == 0) throw new IllegalStateException("No visible native pixels");
        try (FileOutputStream output = new FileOutputStream(new File(dir,"native-simple.png"))) {
            if (!picture.compress(Bitmap.CompressFormat.PNG, 100, output))
                throw new IllegalStateException("Could not encode preview");
        }
        type.getMethod("setActonMode", int.class).invoke(view, 0);
        long start = SystemClock.uptimeMillis();
        int[] actions = {MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE, MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP};
        for (int i=0;i<actions.length;i++) {
            MotionEvent event = MotionEvent.obtain(start,start+i*8,actions[i],20+i*26,175+i*5,0);
            view.onTouchEvent(event);
            event.recycle();
        }
        File edited = new File(dir, "native-edited");
        type.getMethod("saveStrokeData",String.class).invoke(view, edited.getPath());
        File[] bins=edited.listFiles((folder,name)->name.endsWith(".bin"));
        if (bins==null || bins.length!=1) throw new IllegalStateException("Unexpected native output members");
        Class<?> codec=loader.loadClass("com.zykj.view.utils.ProtoFileUtils");
        List<?> strokes=(List<?>)codec.getMethod("loadDataToList",String.class).invoke(codec.getField("INSTANCE").get(null),bins[0].getPath());
        if (strokes.size()!=3) throw new IllegalStateException("Expected 3 paths, got "+strokes.size());
        Bitmap background = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888);
        android.graphics.Canvas sheet = new android.graphics.Canvas(background);
        sheet.drawColor(0xfffcfaf3);
        android.graphics.Paint rule = new android.graphics.Paint();
        rule.setColor(0xffbdc8c3);
        for (int y=40; y<480; y+=40) sheet.drawLine(0,y,640,y,rule);
        type.getMethod("setImageBackground",Bitmap.class).invoke(view,background);
        File nativePage=new File(dir,"simple-with-background");
        type.getMethod("saveData",String.class).invoke(view,nativePage.getPath());
        try (java.util.zip.ZipOutputStream archive = new java.util.zip.ZipOutputStream(
                new FileOutputStream(new File(dir,"native-simple-page.zip")))) {
            for(File member:nativePage.listFiles()) {
                archive.putNextEntry(new java.util.zip.ZipEntry(member.getName()));
                Files.copy(member.toPath(),archive);
                archive.closeEntry();
            }
        }
        Files.copy(bins[0].toPath(),new File(dir,"native-edited.bin").toPath(),
                   java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }
}
