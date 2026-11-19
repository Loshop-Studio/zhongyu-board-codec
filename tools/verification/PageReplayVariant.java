import android.graphics.Matrix;
import android.graphics.Path;
import android.graphics.PathMeasure;
import android.graphics.Paint;
import android.graphics.RectF;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import org.json.*;

/** Exercise each vendor's compiled command scheduler with its own controller
 * and graph factory. Observe the transient drawing surface at seek time. */
public final class PageReplayVariant {
    private static void setter(Object target,Object value) throws Exception {
        Method found=null;
        for(Method m:target.getClass().getSuperclass().getDeclaredMethods()) {
            Class<?>[] args=m.getParameterTypes();
            if(Modifier.isPublic(m.getModifiers()) && m.getReturnType()==void.class &&
                    args.length==1 && args[0].isInstance(value)) {
                if(found!=null)throw new IllegalStateException("ambiguous setter "+m);
                found=m;
            }
        }
        if(found==null)throw new NoSuchMethodException("native setter");
        found.invoke(target,value);
    }
    private static String name(String sig){return sig.substring(0,sig.indexOf('('));}

    static String run(Properties p,Object loader,Object adapter,Object control,File page,File out) throws Exception {
        Class<?> controller=control.getClass(), cls=Class.forName(p.getProperty("thread"));
        Class<?> factory=Class.forName(p.getProperty("factory"));
        Class<?> api=ArtworkVariantProbe.constructor(factory,3).getParameterTypes()[2];
        float[] tip={-1,-1},translation={0};
        boolean cursorProbe=p.containsKey("cursorTimes");
        boolean cameraProbe=p.containsKey("cameraTimes");
        java.lang.reflect.Field cameraField=cameraProbe?adapter.getClass().getDeclaredField(p.getProperty("cameraField")):null;
        if(cameraProbe) cameraField.setAccessible(true);
        Matrix[] transientCamera={null};
        JSONObject[] cursor={null};
        String draw=name(p.getProperty("draw")),redraw=name(p.getProperty("redraw")),end=name(p.getProperty("matrixEnd"));
        Object sink=Proxy.newProxyInstance(api.getClassLoader(),new Class<?>[]{api},(proxy,m,v)->{
            Class<?>[] a=m.getParameterTypes();
            if(cameraProbe && m.getName().equals(p.getProperty("cameraChanging")) && a.length==1 && a[0]==Matrix.class)
                transientCamera[0]=new Matrix((Matrix)v[0]);
            if(m.getName().equals(draw) && a.length==1 && a[0]==boolean.class) return null;
            if(m.getName().equals(redraw) && a.length==0)return null;
            if(a.length==3 && a[0]==Path.class){
                if(cursorProbe && ((Paint)v[1]).getStyle()==Paint.Style.FILL){
                    Path rendered=new Path((Path)v[0]);
                    if(v[2]!=null)rendered.transform((Matrix)v[2]);
                    RectF bounds=new RectF();
                    rendered.computeBounds(bounds,true);
                    cursor[0]=new JSONObject().put("x",(double)bounds.centerX()).put("y",(double)bounds.centerY())
                        .put("width",(double)bounds.width()).put("height",(double)bounds.height())
                        .put("color",((Paint)v[1]).getColor());
                }
                PathMeasure shape=new PathMeasure((Path)v[0],false);
                shape.getPosTan(shape.getLength(),tip,null);return null;
            }
            if(a.length==2 && a[0]==List.class && a[1]==Matrix.class && !m.getName().equals(end)){
                float[] xy={0,0};((Matrix)v[1]).mapPoints(xy);translation[0]=xy[0];return null;
            }
            return m.invoke(control,v);
        });
        Object thread=ArtworkVariantProbe.constructor(cls,0).newInstance();
        setter(thread,loader);setter(thread,adapter);setter(thread,sink);
        ArtworkVariantProbe.method(cls,p.getProperty("path"),1).invoke(thread,page.toString());
        ArtworkVariantProbe.method(cls,p.getProperty("version"),1).invoke(thread,6);
        ArtworkVariantProbe.method(cls,p.getProperty("maximum"),1).invoke(thread,Long.parseLong(p.getProperty("duration","3100")));
        ((Runnable)thread).run();
        Method seek=ArtworkVariantProbe.method(cls,p.getProperty("seek"),1);
        Method snapshot=ArtworkVariantProbe.method(controller,p.getProperty("snapshot"),0);
        out.mkdirs();
        JSONArray list=new JSONArray();
        try {
            int[] times=PageReplayProbe.TIMES;
            if(cursorProbe)times=Arrays.stream(p.getProperty("cursorTimes").split(",")).mapToInt(Integer::parseInt).toArray();
            if(cameraProbe)times=Arrays.stream(p.getProperty("cameraTimes").split(",")).mapToInt(Integer::parseInt).toArray();
            for(int i=0;i<times.length;i++){
                int t=times[i];tip[0]=tip[1]=-1;translation[0]=0;cursor[0]=null;transientCamera[0]=null;
                seek.invoke(thread,(long)t);
                if(cameraProbe){
                    Matrix state=new Matrix((Matrix)cameraField.get(adapter));
                    if(transientCamera[0]!=null)state.postConcat(transientCamera[0]);
                    float[] values=new float[9];state.getValues(values);
                    list.put(new JSONObject().put("ms",t).put("matrix",new JSONArray(values)));
                    continue;
                }
                if(cursorProbe){
                    list.put(new JSONObject().put("ms",t).put("cursor",cursor[0]==null?JSONObject.NULL:cursor[0]));
                    continue;
                }
                ArtworkVariantProbe.capture(control,snapshot,new File(out,"seek-"+i+".bin"));
                list.put(new JSONObject().put("ms",t).put("active_path_end",new JSONArray().put((double)tip[0]).put((double)tip[1]))
                        .put("transient_dx",(double)translation[0]));
            }
        } finally {ArtworkVariantProbe.method(cls,p.getProperty("shutdown"),0).invoke(thread);}
        try(FileWriter writer=new FileWriter(new File(out,"paths.json"))){writer.write(list.toString());}
        return list.length()+(cameraProbe?" native camera checkpoints":cursorProbe?" native cursor checkpoints":" native graph snapshots and transient paths");
    }
}
