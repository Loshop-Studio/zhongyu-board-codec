package local.zy.boardprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.view.View;
import android.widget.FrameLayout;
import java.io.File;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import static local.zy.boardprobe.PptWebViewProbe.ui;

/** Insert a local HTML asset and save through the public recorder view. */
final class PptRecorderProbe {
    private static Object callback(Class<?> fn,LinkedBlockingQueue<Object> queue) {
        return Proxy.newProxyInstance(fn.getClassLoader(),new Class[]{fn},(p,m,arguments)->{
            if(m.getName().equals("invoke")&&arguments!=null&&arguments[0]!=null)queue.add(arguments[0]);
            return null;
        });
    }
    static void save(Instrumentation inst,ClassLoader loader,File apk,File entry,File output) throws Exception {
        Context ctx=inst.getTargetContext();
        Activity screen=inst.startActivitySync(new Intent(ctx,PptWebViewProbe.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        Class<?> type=loader.loadClass("com.zykj.sketch.core.record.SketchRecorderView");
        try{
            View view=ui(inst,()->{
                Context res=NativePlayerProbe.resources(screen,apk);
                View recorder=(View)type.getConstructor(Context.class,android.util.AttributeSet.class).newInstance(res,null);
                FrameLayout root=new FrameLayout(screen);
                root.addView(recorder,new FrameLayout.LayoutParams(640,480));
                screen.setContentView(root);
                return recorder;
            });
            inst.waitForIdleSync();
            LinkedBlockingQueue<Object> replies=new LinkedBlockingQueue<>();
            Method add=java.util.Arrays.stream(type.getMethods()).filter(m->m.getName().equals("addPPT")).findFirst().get();
            Class<?> fn=add.getParameterTypes()[1];
            ui(inst,()->{
                Object config=NativePlayerProbe.field(view,"sketchConfig");
                config.getClass().getMethod("setSourcePath",String.class).invoke(config,output.getPath());
                add.invoke(view,entry.getPath(),callback(fn,replies));
                return null;
            });
            if(replies.poll(10,TimeUnit.SECONDS)==null)throw new AssertionError("No addPPT callback");
            ui(inst,()->{type.getMethod("getRecordPath",fn).invoke(view,callback(fn,replies));return null;});
            if(!output.getPath().equals(replies.poll(10,TimeUnit.SECONDS)))throw new AssertionError("No saved path");
            ui(inst,()->NativePlayerProbe.call(NativePlayerProbe.field(view,"recordControl"),"onDestroy"));
        }finally{ui(inst,()->{screen.finish();return null;});}
    }
}
