package local.zy.boardprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Matrix;
import android.view.View;
import android.widget.FrameLayout;
import java.io.File;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;
import static local.zy.boardprobe.NativePlayerProbe.field;
import static local.zy.boardprobe.NativePlayerProbe.call;
import static local.zy.boardprobe.PptWebViewProbe.ui;

/** Observe graph dimensions and native task times independently of slide HTML. */
final class PptGraphProbe {
    private static JSONArray collect(ClassLoader loader,Object graph,JSONArray layers) throws Exception {
        String kind=graph.getClass().getSimpleName();
        if(kind.equals("WebViewGraph")){
            JSONObject deck=new JSONObject().put("entry",field(graph,"fileName"))
                .put("width",field(graph,"width")).put("height",field(graph,"height"));
            Matrix matrix=(Matrix)loader.loadClass("com.zykj.sketch.core.graph.GraphExtKt")
                .getMethod("getFP2WPRendMatrix",loader.loadClass("com.zykj.sketch.core.graph.Graph"))
                .invoke(null,graph);
            float[] raw=new float[9];matrix.getValues(raw);
            layers.put(deck.put("matrix",new JSONArray(raw)));
        }else if(kind.equals("StrokeGraph"))layers.put("stroke");
        for(Object child:(List<?>)call(graph,"getChild"))collect(loader,child,layers);
        return layers;
    }
    private static void nextFrame(View view) throws Exception {
        java.util.concurrent.CountDownLatch frame=new java.util.concurrent.CountDownLatch(1);
        view.postOnAnimation(frame::countDown);
        if(!frame.await(4,java.util.concurrent.TimeUnit.SECONDS))throw new AssertionError("No Android frame");
    }
    static String run(Instrumentation inst,ClassLoader loader,File apk,File pages) throws Exception {
        Context ctx=inst.getTargetContext();
        Activity screen=inst.startActivitySync(new Intent(ctx,PptWebViewProbe.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        JSONObject out=new JSONObject();
        try {
            java.util.List<String> names=new java.util.ArrayList<>(java.util.Arrays.asList("slides-v2","slides-v3","slides-v4","slides-v5","slides-recording","slides"));
            if(new File(pages,"native-presentation/actions.bin").isFile())names.add("native-presentation");
            for(String name:names){
                android.util.Log.i("PptGraphProbe","loading "+name);
                Class<?> type=loader.loadClass("com.zykj.sketch.core.player.SketchPlayerView");
                View view=ui(inst,()->{
                    Context res=NativePlayerProbe.resources(screen,apk);
                    View player=(View)type.getConstructor(Context.class,android.util.AttributeSet.class).newInstance(res,null);
                    FrameLayout root=new FrameLayout(screen);
                    root.addView(player,new FrameLayout.LayoutParams(640,480));
                    screen.setContentView(root);
                    return player;
                });
                nextFrame(view);
                Object control=field(view,"playControl");
                ui(inst,()->{
                    for(Method method:control.getClass().getMethods())
                        if(method.getName().equals("loadData")&&method.getParameterTypes().length==2&&method.getParameterTypes()[0]==String.class){
                            Class<?> fn=method.getParameterTypes()[1];
                            method.invoke(control,new File(pages,name).getPath(),Proxy.newProxyInstance(loader,new Class[]{fn},(p,m,a)->null));
                            return null;
                        }
                    throw new NoSuchMethodException("loadData");
                });
                Object graph=field(control,"graphControl");
                Class<?> callback=loader.loadClass("com.zykj.sketch.core.data.GraphTask").getMethod("getExecuteVoid").getReturnType();
                JSONArray frames=new JSONArray();
                for(Object task:(List<?>)call(field(control,"renderTask"),"getGraphTask")){
                    ui(inst,()->{
                        callback.getMethod("invoke").invoke(call(task,"getExecuteVoid"));
                        frames.put(new JSONObject().put("ms",call(task,"getStartTime"))
                            .put("layers",collect(loader,call(graph,"getRootGraph"),new JSONArray())));
                        return null;
                    });
                    nextFrame(view);
                }
                android.util.Log.i("PptGraphProbe","observed "+name+" "+frames.length()+" callbacks");
                out.put(name,frames);
                ui(inst,()->call(control,"onDestroy"));
            }
        }finally{ui(inst,()->{screen.finish();return null;});}
        return out.toString();
    }
}
