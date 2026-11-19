package local.zy.boardprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.webkit.WebView;
import android.view.ViewGroup;
import java.io.File;
import java.lang.reflect.Proxy;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;

/** Exercise each shipped view and listener against the same local HTML used in Chromium. */
public final class PptWebViewProbe extends Activity {
    static <T> T ui(Instrumentation inst, Callable<T> action) throws Exception {
        FutureTask<T> task = new FutureTask<>(action);
        new android.os.Handler(android.os.Looper.getMainLooper()).post(task);
        return task.get(12, TimeUnit.SECONDS);
    }

    private static void waitFor(BlockingQueue<String> events, String wanted) throws Exception {
        long end = android.os.SystemClock.elapsedRealtime() + 15000;
        String value;
        do {
            long remaining = end - android.os.SystemClock.elapsedRealtime();
            if (remaining <= 0 || (value = events.poll(remaining, TimeUnit.MILLISECONDS)) == null)
                throw new AssertionError("Timed out waiting for " + wanted);
        } while (!wanted.equals(value));
    }

    private static JSONObject state(Instrumentation inst, WebView view) throws Exception {
        BlockingQueue<String> answer = new LinkedBlockingQueue<>();
        ui(inst, () -> {
            view.evaluateJavascript("({title:document.querySelector('#title').textContent,trace:trace.slice(),"
                + "imageWidth:document.images[0].naturalWidth,background:getComputedStyle(document.querySelector('main')).backgroundColor})", answer::add);
            return null;
        });
        return new JSONObject(answer.poll(12,TimeUnit.SECONDS));
    }

    static String run(Instrumentation inst, ClassLoader loader, File entry) throws Exception {
        Context ctx = inst.getTargetContext();
        Activity screen = inst.startActivitySync(new Intent(ctx,PptWebViewProbe.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        Class<?> type = loader.loadClass("com.zykj.sketch.widgets.PPTWebView");
        Class<?> listener = loader.loadClass("com.zykj.sketch.core.listener.PPTListener");
        WebView view = ui(inst, () -> {
            WebView v = (WebView)type.getConstructor(Context.class).newInstance(screen);
            screen.setContentView(v,new ViewGroup.LayoutParams(720,450));
            return v;
        });
        BlockingQueue<String> finished = new LinkedBlockingQueue<>(), pages = new LinkedBlockingQueue<>();
        java.util.concurrent.atomic.AtomicInteger total = new java.util.concurrent.atomic.AtomicInteger();
        Object callbacks = Proxy.newProxyInstance(loader, new Class[]{listener}, (proxy,method,args) -> {
            switch (method.getName()) {
                case "currentPage": pages.add(String.valueOf(args[0])); break;
                case "totalPageCount": total.set((Integer)args[0]); break;
                case "onPageFinished": finished.add(String.valueOf(view.getUrl())); break;
            }
            return null;
        });
        String fallback = "file:///android_asset/ppt/demo.html";
        try {
            ui(inst, () -> {
                type.getMethod("setListener", listener).invoke(view, callbacks);
                type.getMethod("loadSlider", String.class).invoke(view, entry.getPath());
                return null;
            });
            // A missing asset can finish with a null visible URL on Android 11.
            // The host checks the AndroidProtocolHandler error from this exact PID.
            String fallbackResult=finished.poll(2500,TimeUnit.MILLISECONDS);
            pages.clear();
            // loadSlider's final destination is absent in the APK. Navigate explicitly
            // so that the original control methods and JavaScript interface can be observed.
            String supplied = Uri.fromFile(entry).toString();
            ui(inst, () -> {view.loadUrl(supplied);return null;});
            waitFor(pages,"1");
            waitFor(finished,supplied);
            String[] methods = {"nextAction","nextSlide","preAction","goPage","preSlide"};
            int[] expected = {1,2,1,3,2}, steps = {1,0,1,0,0};
            JSONArray states = new JSONArray().put(state(inst,view));
            for(int i=0;i<methods.length;i++){
                String op=methods[i];
                ui(inst, () -> {
                    if(op.equals("goPage")) type.getMethod(op,int.class).invoke(view,3);
                    else type.getMethod(op).invoke(view);
                    return null;
                });
                waitFor(pages,Integer.toString(expected[i]));
                JSONObject s=state(inst,view);
                if(!s.getString("title").equals("Slide "+expected[i]+" / 3 · "+steps[i]) || total.get()!=3)
                    throw new AssertionError(s.toString());
                states.put(s);
            }
            return new JSONObject().put("pid",android.os.Process.myPid()).put("fallbackFinishedUrl",fallbackResult == null ? JSONObject.NULL : fallbackResult).put("explicitFixtureNavigation",true)
                    .put("totalPageCount",total.get()).put("states",states).toString();
        } finally {
            ui(inst, () -> {((ViewGroup)view.getParent()).removeView(view);view.destroy();screen.finish();return null;});
        }
    }
}
