package local.zy.boardprobe;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.os.Bundle;
import android.view.View;
import dalvik.system.DexClassLoader;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;

/** Open the supplied actions.bin with the original recorder and capture its completed graph. */
public final class SketchShapesProbe extends Instrumentation {
    private String[] cases;

    @Override public void onCreate(Bundle options) {
        cases = options.getString("cases").split(",");
        start();
    }

    private <T> T onUi(Callable<T> body) throws Exception {
        FutureTask<T> task = new FutureTask<>(body);
        runOnMainSync(task);
        return task.get();
    }

    private String inspect(File dir, File apk, ClassLoader loader) throws Exception {
        Context resources = NativePlayerProbe.resources(getTargetContext(), apk);
        Object[] root = new Object[1];
        CountDownLatch ready = new CountDownLatch(1);
        Object control = onUi(() -> {
            Class<?> recorder = loader.loadClass("com.zykj.sketch.core.record.SketchRecorderView");
            View view = (View)recorder.getConstructor(Context.class, android.util.AttributeSet.class)
                .newInstance(resources, null);
            view.measure(View.MeasureSpec.makeMeasureSpec(640, View.MeasureSpec.EXACTLY),
                         View.MeasureSpec.makeMeasureSpec(480, View.MeasureSpec.EXACTLY));
            view.layout(0, 0, 640, 480);
            Object config = NativePlayerProbe.field(view, "sketchConfig");
            config.getClass().getMethod("setSourcePath", String.class).invoke(config, dir.toString());
            Object record = NativePlayerProbe.field(view, "recordControl");
            for (Method method : record.getClass().getMethods()) {
                if (!method.getName().equals("loadData") || method.getParameterCount() != 3) continue;
                Class<?>[] types = method.getParameterTypes();
                Object viewBack = Proxy.newProxyInstance(loader, new Class<?>[]{types[1]}, (p,m,a) -> null);
                Object finish = Proxy.newProxyInstance(loader, new Class<?>[]{types[2]}, (p,m,a) -> {
                    if (m.getName().equals("invoke") && a != null && a.length == 1) {
                        root[0] = a[0];
                        ready.countDown();
                    }
                    return null;
                });
                method.invoke(record, dir.toString(), viewBack, finish);
                return record;
            }
            throw new NoSuchMethodException("RecordControl.loadData");
        });
        if (!ready.await(15, TimeUnit.SECONDS)) throw new AssertionError("Missing recorder callback");
        return onUi(() -> {
            String recorded = capture(root[0], loader, dir, "recorder");
            if (dir.getName().equals("jpeg-v1")) {
                int images = (Integer)root[0].getClass().getMethod("childTypeNumber",String.class)
                    .invoke(root[0],"com.zykj.sketch.core.graph.ImageGraph");
                NativePlayerProbe.call(control, "onDestroy");
                return recorded + "/images=" + images;
            }
            NativePlayerProbe.call(control, "onDestroy");
            String played = NativePlayerProbe.run(getTargetContext(), loader, dir.getParentFile(),
                dir.getName(), true, apk, graph -> capture(graph, loader, dir, "player"));
            return recorded + "/" + played;
        });
    }

    private static String capture(Object root, ClassLoader loader, File dir, String name) throws Exception {
        JSONArray paths = NativePlayerProbe.ink(root, loader, new JSONArray());
        Bitmap pixels = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(pixels);
        canvas.drawColor(Color.WHITE);
        root.getClass().getMethod("onDraw", Canvas.class).invoke(root, canvas);
        try (FileOutputStream image = new FileOutputStream(new File(dir, name + ".png"));
             FileOutputStream data = new FileOutputStream(new File(dir, name + ".json"))) {
            if (!pixels.compress(Bitmap.CompressFormat.PNG, 100, image)) throw new AssertionError("PNG");
            data.write(paths.toString().getBytes("UTF-8"));
        }
        return name + "=" + paths.length();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            File files = getTargetContext().getFilesDir();
            File apk = new File(files, "reader.apk");
            ClassLoader loader = new DexClassLoader(apk.toString(), getTargetContext().getCodeCacheDir().toString(),
                null, getClass().getClassLoader());
            for (String name : cases) result.putString(name, inspect(new File(files, name), apk, loader));
            finish(-1, result);
        } catch (Throwable error) {
            result.putString("stream", android.util.Log.getStackTraceString(error));
            finish(0, result);
        }
    }
}
