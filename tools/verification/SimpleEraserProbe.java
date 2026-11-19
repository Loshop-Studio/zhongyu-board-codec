package local.zy.simpleeraser;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Matrix;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;
import dalvik.system.DexClassLoader;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Replay page-coordinate contacts through each original View, then save the surviving paths with its writer.
 */
public final class SimpleEraserProbe extends Instrumentation {
    private Bundle options;
    @Override
    public void onCreate(Bundle args) {
        options = args;
        start();
    }
    private static void picture(Bitmap bitmap, File file) throws Exception {
        try (FileOutputStream out = new FileOutputStream(file)) {
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, out))
                throw new AssertionError("PNG");
        }
    }
    private void replay() throws Exception {
        Context ctx = getTargetContext();
        File root = ctx.getFilesDir(), input = new File(root, "input");
        ClassLoader cl = new DexClassLoader(new File(root, "target.apk").toString(),
            ctx.getCodeCacheDir().toString(), null, getClass().getClassLoader());
        Class<?> type = cl.loadClass("com.zykj.view.simpleBoard.SimpleBoardView");
        boolean mistake = options.getString("app").equals("mistake");
        JSONArray cases = new JSONArray(
            new String(Files.readAllBytes(new File(root, "cases.json").toPath()), StandardCharsets.UTF_8));
        for (int i = 0; i < cases.length(); i++) {
            JSONObject cfg = cases.getJSONObject(i);
            File out = new File(root, "results/" + cfg.getString("name"));
            out.mkdirs();
            View view = (View) type.getConstructor(Context.class, android.util.AttributeSet.class)
                            .newInstance(ctx, null);
            view.measure(View.MeasureSpec.makeMeasureSpec(320, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(240, View.MeasureSpec.EXACTLY));
            view.layout(0, 0, 320, 240);
            type.getMethod(mistake ? "loadData" : "g", String.class).invoke(view, input.toString());
            Object config = type.getMethod("getSimpleBoardConfig").invoke(view);
            Method size = config.getClass().getMethod(mistake ? "getEraserSize" : "d");
            if ((Float) size.invoke(config) != 40f)
                throw new AssertionError("default radius");
            if (cfg.has("radius"))
                config.getClass()
                    .getMethod(mistake ? "setEraserSize" : "k", float.class)
                    .invoke(config, (float) cfg.getDouble("radius"));
            float zoom = (float) cfg.optDouble("zoom", 1);
            if (zoom != 1)
                type.getMethod(mistake ? "setScale" : "j", float.class).invoke(view, zoom);
            Matrix camera = null;
            for (Field f : type.getDeclaredFields())
                if (f.getType() == Matrix.class) {
                    f.setAccessible(true);
                    camera = (Matrix) f.get(view);
                    break;
                }
            if (camera == null || Math.abs(camera.mapRadius(1) - zoom) > .001)
                throw new AssertionError("camera zoom");
            type.getMethod("setActonMode", int.class).invoke(view, 2);
            JSONArray events = cfg.getJSONArray("contacts");
            long start = SystemClock.uptimeMillis();
            for (int n = 0; n < events.length(); n++) {
                JSONArray e = events.getJSONArray(n);
                float[] xy = {(float) e.getDouble(1), (float) e.getDouble(2)};
                camera.mapPoints(xy);
                MotionEvent touch = MotionEvent.obtain(start, start + n * 10, e.getInt(0), xy[0], xy[1], 0);
                try {
                    view.onTouchEvent(touch);
                } finally {
                    touch.recycle();
                }
            }
            type.getMethod(mistake ? "saveData" : "i", String.class).invoke(view, out.toString());
            File[] saved = out.listFiles(f -> f.getName().endsWith(".bin"));
            if (saved == null || saved.length != 1)
                throw new AssertionError("BIN");
            Files.move(saved[0].toPath(), new File(out, "result.bin").toPath(),
                java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            if (cfg.optBoolean("picture"))
                picture((Bitmap) type.getMethod(mistake ? "buildBitmap" : "d").invoke(view),
                    new File(out, "page.png"));
        }
    }
    @Override
    public void onStart() {
        Throwable[] errors = {null};
        runOnMainSync(() -> {
            try {
                replay();
            } catch (Throwable t) {
                errors[0] = t;
            }
        });
        Bundle result = new Bundle();
        if (errors[0] == null)
            finish(-1, result);
        else {
            result.putString("error", Log.getStackTraceString(errors[0]));
            finish(0, result);
        }
    }
}
