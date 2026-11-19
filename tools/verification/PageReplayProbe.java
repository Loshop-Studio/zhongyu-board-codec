import android.graphics.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import org.json.JSONArray;
import org.json.JSONObject;

/** Feed real seek times to the original CommandThread. Capture its transient
 * draw callbacks and render the committed graph with the original renderer. */
public final class PageReplayProbe {
    static final String CORE = ArtworkCommandProbe.CORE;
    static final int[] TIMES = {0,199,201,399,400,699,700,999,1000,1299,1300,
            1799,1800,1899,1900,2200,2400,2599,2600,3100,700,1300,2600};
    static Object call(Object target,String method,Object... args) throws Exception {
        return ArtworkCommandProbe.call(target,method,args);
    }
    public static String run(File page,File output) throws Exception {
        output.mkdirs();
        Object loader=ArtworkCommandProbe.make(CORE+"loader.CacheSourceLoader");
        call(loader,"initPath",page.toString());
        Object adapter=ArtworkCommandProbe.make(CORE+"canvas.MatrixAdapter");
        String views=CORE+"canvas.view.";
        Object layers=ArtworkCommandProbe.make(views+"RenderLayer",
                ArtworkCommandProbe.layer(Class.forName(views+"BackgroundLayer")),
                ArtworkCommandProbe.layer(Class.forName(views+"FixLayer")),null,null);
        Object control=ArtworkCommandProbe.make(CORE+"canvas.control.GraphControl",adapter,layers,
                ArtworkCommandProbe.make("com.zykj.blackboard.bean.BoardConfig",640,480));
        call(control,"isDraw",false);
        Class<?> graphApi=Class.forName(CORE+"canvas.control.IGraphControl");
        Path[] active={null};
        Paint[] pen={null};
        Matrix[] move={null};
        int[] paper={-1};
        Object facade=Proxy.newProxyInstance(graphApi.getClassLoader(),new Class<?>[]{graphApi},(p,m,v)->{
            switch(m.getName()){
                case "getIsDraw":return true;
                case "isDraw":return m.getReturnType()==Boolean.TYPE?Boolean.TRUE:null;
                case "reDrawFixView":case "updateBackgroundLineConfig":return null;
                case "updateBackgroundColor":paper[0]=(Integer)v[0];return null;
                case "translationStart":move[0]=null;return null;
                case "translation":move[0]=new Matrix((Matrix)v[1]);return null;
                case "drawPath":
                    active[0]=new Path((Path)v[0]);pen[0]=new Paint((Paint)v[1]);return null;
                default:return m.invoke(control,v);
            }
        });
        Object thread=ArtworkCommandProbe.make(CORE+"play.CommandThread");
        call(thread,"setSourceLoader",loader);call(thread,"setGraphControl",facade);
        call(thread,"setMatrixAdapter",adapter);call(thread,"setPageRootPath",page.toString());
        call(thread,"setVersion",6);call(thread,"setMaxPlayTime",3100L);
        ((Runnable)thread).run(); // Initializes the original factory before the first seek.
        JSONArray rows=new JSONArray();
        try {
            for(int time:TIMES){
                active[0]=null;move[0]=null;paper[0]=-1;
                call(thread,"seekTo",(long)time);
                Object root=call(control,"rootGraph");
                Bitmap image=Bitmap.createBitmap(640,480,Bitmap.Config.ARGB_8888);
                image.eraseColor(paper[0]);Canvas canvas=new Canvas(image);
                JSONArray ids=new JSONArray();String text="";float offset=0;
                if(root!=null)for(Object node:(List<?>)call(root,"getChildGraph")){
                    String id=(String)call(node,"getId");ids.put(id);
                    Matrix extra=(Matrix)call(adapter,"getCameraMatrix");
                    if(id.equals("ink") && move[0]!=null)extra=new Matrix(move[0]);
                    call(node,"render",canvas,extra);
                    if(id.equals("title"))text=(String)call(node,"getContent");
                    if(id.equals("ink")){
                        float[] xy={0,0};((Matrix)call(node,"getRenderMatrix")).mapPoints(xy);
                        extra.mapPoints(xy);offset=xy[0];
                    }
                }
                double endX=-1,endY=-1;
                if(active[0]!=null){
                    canvas.drawPath(active[0],pen[0]);
                    PathMeasure shape=new PathMeasure(active[0],false);float[] xy=new float[2];
                    if(shape.getPosTan(shape.getLength(),xy,null)){endX=xy[0];endY=xy[1];}
                }
                rows.put(new JSONObject().put("ms",time).put("graph_ids",ids).put("text",text)
                        .put("ink_dx",offset).put("active_path_end",new JSONArray().put(endX).put(endY)));
                try(FileOutputStream out=new FileOutputStream(new File(output,"frame-"+time+".png"))){
                    image.compress(Bitmap.CompressFormat.PNG,100,out);
                }
                image.recycle();
            }
            // The normal player uses a 16-ms tick. Unlike seekTo, readCommand
            // applies isPlay=false immediately without consuming its delay.
            call(thread,"reset");call(thread,"setPageRootPath",page.toString());call(thread,"startPlay");
            JSONArray forward=new JSONArray();
            for(int ms=0; ms<=2656;ms+=16) {
                ((Runnable)thread).run();
                if(ms==1792 || ms==1808 || ms==1888 || ms==2608){
                    Object root=call(control,"rootGraph");
                    Object label=call(root,"findById","title");
                    forward.put(new JSONObject().put("ms",ms).put("text",label==null?"":call(label,"getContent")));
                }
                Thread.sleep(16);
            }
            try(FileWriter file=new FileWriter(new File(output,"forward.json"))){file.write(forward.toString(2));}
        } finally {call(thread,"shutdown");}
        try(FileWriter file=new FileWriter(new File(output,"frames.json"))){file.write(rows.toString(2));}
        return rows.length()+" native seeks";
    }
}
