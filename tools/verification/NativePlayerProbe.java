package local.zy.boardprobe;

import android.content.Context;
import android.view.View;
import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Proxy;
import java.util.List;

/** Load a recording through the original player and execute its scheduled drawing callbacks. */
final class NativePlayerProbe {
    static Object field(Object object,String name) throws Exception {
        Field f=object.getClass().getDeclaredField(name);
        f.setAccessible(true);
        return f.get(object);
    }
    static Object call(Object object,String name) throws Exception {
        return object.getClass().getMethod(name).invoke(object);
    }
    private static int strokes(Object snapshot) throws Exception {
        int count="STROKE_GRAPH".equals(String.valueOf(call(snapshot,"getGraphType"))) ? 1 : 0;
        for(Object child:(List<?>)call(snapshot,"getChildGraphList")) count+=strokes(child);
        return count;
    }
    static org.json.JSONArray ink(Object graph,ClassLoader loader,org.json.JSONArray strokes) throws Exception {
        if (graph.getClass().getSimpleName().equals("StrokeGraph")) {
            Object message=call(graph,"getSnapshot");
            Object extra=call(message,"getExtra");
            Class<?> type=loader.loadClass("com.zykj.sketch.GraphSnapshot$Touch");
            Object touch=extra.getClass().getMethod("unpack",Class.class).invoke(extra,type);
            android.graphics.Matrix world=(android.graphics.Matrix)loader.loadClass("com.zykj.sketch.core.graph.GraphExtKt")
                    .getMethod("getFP2WPMatrix",loader.loadClass("com.zykj.sketch.core.graph.Graph")).invoke(null,graph);
            org.json.JSONArray points=new org.json.JSONArray();
            for(Object point:(List<?>)call(touch,"getPointFList")) {
                float[] xy={(Float)call(point,"getX"),(Float)call(point,"getY")};
                world.mapPoints(xy);
                points.put(new org.json.JSONArray().put(xy[0]).put(xy[1]));
            }
            strokes.put(points);
        }
        for(Object child:(List<?>)call(graph,"getChild")) ink(child,loader,strokes);
        return strokes;
    }
    private static void layers(Object graph,ClassLoader loader,org.json.JSONArray result) throws Exception {
        String type=graph.getClass().getSimpleName();
        if (type.equals("ImageGraph")) {
            android.graphics.RectF bounds=(android.graphics.RectF)call(graph,"getOutRect");
            android.graphics.Matrix matrix=(android.graphics.Matrix)loader.loadClass("com.zykj.sketch.core.graph.GraphExtKt")
                .getMethod("getFP2WPRendMatrix",loader.loadClass("com.zykj.sketch.core.graph.Graph")).invoke(null,graph);
            float[] corners={0,0,bounds.width(),0,bounds.width(),bounds.height(),0,bounds.height()};
            matrix.mapPoints(corners);
            result.put(new org.json.JSONObject().put("image",call(graph,"getFileName"))
                       .put("corners",new org.json.JSONArray(corners)));
        } else if (type.equals("StrokeGraph")) result.put("stroke");
        for(Object child:(List<?>)call(graph,"getChild")) layers(child,loader,result);
    }
    static Context resources(Context context,File apk) throws Exception {
        android.content.pm.PackageManager pm=context.getPackageManager();
        android.content.pm.ApplicationInfo info=pm.getPackageArchiveInfo(apk.getPath(),0).applicationInfo;
        info.sourceDir=info.publicSourceDir=apk.getPath();
        final android.content.res.Resources resources=pm.getResourcesForApplication(info);
        return new android.content.ContextWrapper(context) {
            @Override public android.content.res.Resources getResources(){return resources;}
            @Override public android.content.res.AssetManager getAssets(){return resources.getAssets();}
        };
    }
    static String run(Context context,ClassLoader loader,File dir,String folder,boolean finalOnly) throws Exception {
        return run(context,loader,dir,folder,finalOnly,new File(dir,"mistake.apk"));
    }
    static String run(Context context,ClassLoader loader,File dir,String folder,boolean finalOnly,File apk) throws Exception {
        return run(context,loader,dir,folder,finalOnly,apk,null);
    }
    interface FinalGraph { String inspect(Object root) throws Exception; }
    static String run(Context context,ClassLoader loader,File dir,String folder,boolean finalOnly,File apk,FinalGraph finalGraph) throws Exception {
        Context originalResources=resources(context,apk);
        Class<?> player=loader.loadClass("com.zykj.sketch.core.player.SketchPlayerView");
        View view=(View)player.getConstructor(Context.class,android.util.AttributeSet.class).newInstance(originalResources,null);
        view.measure(View.MeasureSpec.makeMeasureSpec(640,View.MeasureSpec.EXACTLY),
                     View.MeasureSpec.makeMeasureSpec(480,View.MeasureSpec.EXACTLY));
        view.layout(0,0,640,480);
        Object control=field(view,"playControl");
        java.lang.reflect.Method load=null;
        for (java.lang.reflect.Method method:control.getClass().getMethods()) {
            Class<?>[] parameters=method.getParameterTypes();
            if (method.getName().equals("loadData") && parameters.length==2 && parameters[0]==String.class) {
                load=method;
                break;
            }
        }
        if (load==null) throw new NoSuchMethodException("PlayControl.loadData");
        Class<?> function=load.getParameterTypes()[1];
        Object finished=Proxy.newProxyInstance(loader,new Class<?>[]{function},(p,m,args)->null);
        try {
            load.invoke(control,new File(dir,folder).getPath(),finished);
            Object graph=field(control,"graphControl");
            Object task=field(control,"renderTask");
            StringBuilder trace=new StringBuilder();
            Class<?> callback=loader.loadClass("com.zykj.sketch.core.data.GraphTask").getMethod("getExecuteVoid").getReturnType();
            org.json.JSONArray frames=new org.json.JSONArray();
            boolean images=folder.contains("image") || folder.equals("illustration");
            boolean capture=images || folder.contains("transform");
            for (Object entry:(List<?>)call(task,"getGraphTask")) {
                long ms=((Number)call(entry,"getStartTime")).longValue();
                callback.getMethod("invoke").invoke(call(entry,"getExecuteVoid"));
                if (finalGraph != null) continue;
                if (capture) {
                    Object root=call(graph,"getRootGraph");
                    float[] values=new float[9];
                    ((android.graphics.Matrix)call(root,"getMatrix")).getValues(values);
                    org.json.JSONObject frame=new org.json.JSONObject().put("ms",ms)
                        .put("matrix",new org.json.JSONArray(values)).put("strokes",ink(root,loader,new org.json.JSONArray()));
                    if (images) {
                        org.json.JSONArray ordered=new org.json.JSONArray();
                        layers(root,loader,ordered);
                        frame.put("layers",ordered);
                    }
                    frames.put(frame);
                    continue;
                }
                if (ms!=700 && ms!=900 && ms!=950 && ms!=1200 && ms!=1950 && ms!=2000) continue;
                Object snapshot=call(call(call(graph,"getRootGraph"),"getSnapshotBuild"),"build");
                trace.append(ms).append("ms=").append(strokes(snapshot)).append(" ");
            }
            if (finalGraph != null) return finalGraph.inspect(call(graph,"getRootGraph"));
            if (capture) {
                if (finalOnly) {
                    android.graphics.Bitmap bmp=android.graphics.Bitmap.createBitmap(640,480,android.graphics.Bitmap.Config.ARGB_8888);
                    android.graphics.Canvas canvas=new android.graphics.Canvas(bmp);
                    canvas.drawColor(android.graphics.Color.WHITE);
                    Object root=call(graph,"getRootGraph");
                    root.getClass().getMethod("onDraw",android.graphics.Canvas.class).invoke(root,canvas);
                    try (java.io.FileOutputStream png=new java.io.FileOutputStream(new File(dir,folder+"-native.png"))) {
                        bmp.compress(android.graphics.Bitmap.CompressFormat.PNG,100,png);
                    }
                }
                try (java.io.FileOutputStream file=new java.io.FileOutputStream(new File(dir,folder+"-frames.json"))) {
                    file.write(frames.toString().getBytes("UTF-8"));
                }
                return "native transform frames="+frames.length();
            }
            if (finalOnly) {
                Object snapshot=call(call(call(graph,"getRootGraph"),"getSnapshotBuild"),"build");
                return "durationMs="+call(task,"getProgress")+" strokes="+strokes(snapshot);
            }
            return trace.toString().trim();
        } finally {
            call(control,"onDestroy");
        }
    }
}
