import android.graphics.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;

/** Runs inside the unmodified mistake-book class loader. Only the two view-layer
 * callbacks are inert, so the controller can render onto an offscreen bitmap. */
public final class ArtworkCommandProbe {
    static final String CORE = "com.zykj.blackboard.core.";
    static Object call(Object target,String name,Object... args) throws Exception {
        return BoardProbe.call(target,name,args);
    }
    static Object singleton(String name) throws Exception {
        return Class.forName(name).getField("INSTANCE").get(null);
    }
    static Object make(String cls,Object... args) throws Exception {
        for(Constructor<?> c:Class.forName(cls).getConstructors()) {
            if(c.getParameterTypes().length!=args.length)continue;
            try { return c.newInstance(args); } catch(IllegalArgumentException different) {}
        }
        throw new NoSuchMethodException(cls);
    }
    static Object layer(Class<?> type) {
        return Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(p,m,args)->{
            if(m.getReturnType()==Rect.class)return new Rect(0,0,800,600);
            if(m.getReturnType()==boolean.class)return false;
            return null;
        });
    }
    static Object snapshot(File page, Object loader) throws Exception {
        try(InputStream input=new FileInputStream(new File(page,"snapshot.bin"))) {
            Object msg=call(Class.forName("com.zykj.board.EzyPageSnapshot$PageSnapshot"),"parseFrom",input);
            return call(singleton("com.zykj.blackboard.utils.GraphUtils"),"buildGraph",loader,call(msg,"getGraphSnapshot"));
        }
    }
    static void check(boolean condition,String label) {
        if(!condition)throw new IllegalStateException(label);
    }
    static void position(Object node,float x,float y) throws Exception {
        float[] xy={0,0};
        ((Matrix)call(node,"getRenderMatrix")).mapPoints(xy);
        check(x==xy[0] && y==xy[1],"position "+Arrays.toString(xy));
    }
    static void textState(Object root, boolean moved) throws Exception {
        Object text=call(root,"findById","title");
        Paint paint=(Paint)call(text,"getPaint");
        check("Board 42".equals(call(text,"getContent")) && paint.getColor()==0xff164e91 && paint.getTextSize()==36,"text content/paint");
        position(text,moved?72:40,moved?47:35);
    }
    static void ovalState(Object root) throws Exception {
        Object oval=call(root,"findById","oval");
        Paint p=(Paint)call(oval,"getPaint");
        check(p.getStrokeWidth()==7 && p.getStyle()==Paint.Style.STROKE && p.getColor()==0xff794523,"oval paint");
        check(((RectF)call(oval,"getOriginalRectF")).equals(new RectF(0,0,168,82)),"oval bounds");
    }
    static void polygonState(Object root,boolean moved) throws Exception {
        Object poly=call(root,"findById","triangle");
        List<?> points=(List<?>)call(poly,"getPointList");
        check(points.equals(Arrays.asList(new PointF(0,80),new PointF(60,5),new PointF(110,25),new PointF(95,80))),"polygon points "+points);
        position(poly,moved?248:230,moved?144:150);
    }
    static Bitmap artwork(Object root) throws Exception {
        Bitmap image=Bitmap.createBitmap(800,600,Bitmap.Config.ARGB_8888);
        image.eraseColor(0xffffffff);
        Canvas canvas=new Canvas(image);
        for(String id:new String[]{"title","oval","triangle"})
            call(call(root,"findById",id),"render",canvas,new Matrix());
        return image;
    }
    // Native TextGraph, GeometryGraph and ImageGraph load their durable sources
    // lazily on first render. Measure each new node before inspecting its data.
    static Bitmap createdArtwork(Object root, List<String> ids) throws Exception {
        Bitmap output=Bitmap.createBitmap(800,600,Bitmap.Config.ARGB_8888);
        output.eraseColor(0xffffffff);
        Canvas canvas=new Canvas(output);
        String[] kinds={"text","oval","rectangle","triangle","image"};
        int[][] boxes={{40,290,180,58},{65,385,90,72},{235,380,105,80},{405,375,105,88},{590,355,100,100}};
        for(int i=0;i<ids.size();i++){
            String id=ids.get(i);
            check(id.startsWith("web-"+kinds[i]+"-"),"draw order "+id);
            Object node=call(root,"findById",id);
            int[] area=boxes[i];
            position(node,area[0],area[1]);
            RectF bounds=(RectF)call(node,"getOriginalRectF");
            if(i==4)check(bounds.width()==100 && bounds.height()>0,"image bounds "+bounds);
            else check(bounds.equals(new RectF(0,0,area[2],area[3])),"bounds "+id+" "+bounds);
            call(node,"render",canvas,new Matrix());
            int ink=0;
            for(int y=area[1];y<area[1]+area[3];y++)
                for(int x=area[0];x<area[0]+area[2];x++)
                    if(output.getPixel(x,y)!=0xffffffff) ink++;
            check(ink>100,"node rendered "+ink+" visible pixels "+id);
            if(i==0) {
                check("Board 17".equals(call(node,"getContent")),"text content");
                Paint paint=(Paint)call(node,"getPaint");
                check(paint.getColor()==0xff213836 && paint.getTextSize()==28,"text paint");
            } else if(i<4) {
                check(((Integer)call(node,"getGeometryType"))==(i==1?0:1),"geometry kind "+id);
                check(((List<?>)call(node,"getPointList")).size()==(i==1?0:i==2?4:3),"polygon vertex count "+id);
                Paint paint=(Paint)call(node,"getPaint");
                check(paint.getStyle()==Paint.Style.STROKE && paint.getStrokeWidth()==3,"outline "+id);
            } else {
                check(new File((String)call(node,"getFilePath")).getName().equals("tiles-2.png"),"image resource");
            }
        }
        return output;
    }
    /** Start each page with an empty controller. Its first ADD must build the
     * root, and each subsequent source must render just as the snapshot does. */
    public static String newNotebook(File note) throws Exception {
        Object source=singleton(CORE+"data.SourceLoad");
        List<?> pages=(List<?>)call(call(source,"getPageRouter",note.toString()),"getPageInfoList");
        check(pages.size()==2,"page count "+pages.size());
        List<Integer> visible=new ArrayList<>();
        int i=0;
        for(Object info:pages){
            check(((Integer)call(info,"getPageIndex"))==i,"page index");
            File page=new File(note,(String)call(info,"getName"));
            Object loader=make(CORE+"loader.CacheSourceLoader");
            call(loader,"initPath",page.toString());
            Object adapter=make(CORE+"canvas.MatrixAdapter");
            String views=CORE+"canvas.view.";
            Object layers=make(views+"RenderLayer",layer(Class.forName(views+"BackgroundLayer")),layer(Class.forName(views+"FixLayer")),null,null);
            Object control=make(CORE+"canvas.control.GraphControl",adapter,layers,make("com.zykj.blackboard.bean.BoardConfig",1200,900));
            call(control,"isDraw",false);
            Object executor=make(CORE+"execute.version6.CommandExecuteFactory6",loader,adapter,control);
            List<Integer> kinds=new ArrayList<>();
            Object refs=call(source,"getRouter",page.toString());
            for(Object ref:(List<?>)call(refs,"getCommandRecordList")){
                Object commands=call(source,"getCommandRecord",page.toString(),call(ref,"getFileName"),call(ref,"getValidate"));
                for(Object command:(List<?>)call(commands,"getCommandInfoList")){
                    call(executor,"executeCommand",false,command,0L);
                    kinds.add((Integer)call(command,"getCommandEnumValue"));
                }
            }
            check(kinds.equals(i==0?Arrays.asList(1,1):Arrays.asList(1,1,3)),"per-page commands "+kinds);
            Bitmap[] images=new Bitmap[2];
            Object[] roots={call(control,"rootGraph"),snapshot(page,loader)};
            for(int k=0;k<roots.length;k++){
                List<?> children=(List<?>)call(roots[k],"getChildGraph");
                check(children.size()==1,"unexpected number of children");
                Object graph=children.get(0);
                check(graph.getClass().getSimpleName().equals(i==0?"StrokeGraph":"TextGraph"),"node type "+graph.getClass());
                images[k]=Bitmap.createBitmap(1200,900,Bitmap.Config.ARGB_8888);
                images[k].eraseColor(0xffffffff);
                call(graph,"render",new Canvas(images[k]),new Matrix());
                if(i==1)check("Page two".equals(call(graph,"getContent")),"second-page text");
            }
            check(images[0].sameAs(images[1]),"page "+i+" differs by load path");
            int ink=0;
            int[] pixels=new int[1200*900];images[0].getPixels(pixels,0,1200,0,0,1200,900);
            for(int color:pixels)if(color!=0xffffffff)ink++;
            check(ink>100,"empty page "+i);visible.add(ink);
            i++;
        }
        return "two fresh native controllers replayed both root commands, one stroke and one text, matching snapshot RGBA; visible pixels="+visible;
    }
    static Bitmap transformedImage(Object root, boolean dragged) throws Exception {
        Object node = call(root, "findById", "image");
        Matrix matrix = (Matrix)call(node, "getRenderMatrix");
        float[] pts = {52.5f,52.5f, 53.5f,52.5f, 52.5f,53.5f};
        matrix.mapPoints(pts);
        float cx = dragged ? 572.5f : 512.5f, cy = dragged ? 230.5f : 190.5f;
        check(Math.abs(pts[0]-cx)<2 && Math.abs(pts[1]-cy)<2, "centre "+Arrays.toString(pts));
        check(Math.abs(pts[2]-pts[0])<.001 && Math.abs(pts[3]-pts[1]-1.5)<.001 &&
              Math.abs(pts[4]-pts[0]+1.5)<.001 && Math.abs(pts[5]-pts[1])<.001, "rotated basis vectors");
        Bitmap bmp = Bitmap.createBitmap(800,600,Bitmap.Config.ARGB_8888);
        bmp.eraseColor(0xffffffff);
        call(node,"render",new Canvas(bmp),new Matrix());
        check(new File((String)call(node,"getFilePath")).getName().equals("tiles.png"),"original image");
        int painted=0;
        for(int y=0;y<bmp.getHeight();y++)for(int x=0;x<bmp.getWidth();x++)
            if(bmp.getPixel(x,y)!=0xffffffff)painted++;
        check(painted>23000 && painted<26000,"image pixels "+painted);
        return bmp;
    }
    public static String run(File base,File edited,File output,String scenario) throws Exception {
        boolean creation = scenario.equals("create"), imageTransform = scenario.equals("image");
        Object loader=make(CORE+"loader.CacheSourceLoader");
        call(loader,"initPath",edited.toString());
        Object root=snapshot(base,loader);
        Object adapter=make(CORE+"canvas.MatrixAdapter");
        String view=CORE+"canvas.view.";
        Object layers=make(view+"RenderLayer",layer(Class.forName(view+"BackgroundLayer")),layer(Class.forName(view+"FixLayer")),null,null);
        Object control=make(CORE+"canvas.control.GraphControl",adapter,layers,make("com.zykj.blackboard.bean.BoardConfig",800,600));
        call(control,"isDraw",false);
        call(control,"init",root);
        Object executor=make(CORE+"execute.version6.CommandExecuteFactory6",loader,adapter,control);
        Object source=singleton(CORE+"data.SourceLoad");
        Object refs=call(source,"getRouter",edited.toString());
        List<Integer> sequence=new ArrayList<>();
        List<String> ids=new ArrayList<>();
        for(Object ref:(List<?>)call(refs,"getCommandRecordList")) {
            Object data=call(source,"getCommandRecord",edited.toString(),call(ref,"getFileName"),call(ref,"getValidate"));
            for(Object command:(List<?>)call(data,"getCommandInfoList")) {
                int kind=(Integer)call(command,"getCommandEnumValue");
                sequence.add(kind);
                call(executor,"executeCommand",false,command,0L);
                root=call(control,"rootGraph");
                if(imageTransform){
                    check(kind==3,"expected a graph matrix");
                    transformedImage(root, sequence.size()==2);
                    continue;
                }
                if(creation){
                    if(kind==1) {
                        Object graphData=call(Class.forName("com.zykj.board.EzyCommand$CommandSource$CommandInfo$GraphData"),"parseFrom",call(command,"getData"));
                        String id=(String)call(graphData,"getGraphId");
                        ids.add(id);
                        position(call(root,"findById",id),0,0);
                    }
                    continue;
                }
                switch(sequence.size()) {
                    case 1: textState(root,false);break;
                    case 2: textState(root,true);break;
                    case 3: ovalState(root);break;
                    case 4: polygonState(root,false);break;
                    case 5: polygonState(root,true);break;
                }
            }
        }
        if(imageTransform){
            check(sequence.equals(Arrays.asList(3,3)),"image matrix count "+sequence);
            Bitmap live=transformedImage(root,true), restored=transformedImage(snapshot(edited,loader),true);
            check(live.sameAs(restored),"native render differs by load path");
            try(OutputStream out=new FileOutputStream(output)){live.compress(Bitmap.CompressFormat.PNG,100,out);}
            return "native replay vs snapshot identical: two image matrix commands, centre, 90 degree basis, uniform scale 1.5, original tiles.png and painted pixels verified";
        }
        if(creation){
            check(sequence.equals(Arrays.asList(1,3,1,3,1,3,1,3,1,3)),"artwork insert sequence "+sequence);
            Bitmap live=createdArtwork(root,ids), fromDisk=createdArtwork(snapshot(edited,loader),ids);
            check(live.sameAs(fromDisk),"rendered command replay and restored artwork differ");
            try(OutputStream out=new FileOutputStream(output)){live.compress(Bitmap.CompressFormat.PNG,100,out);}
            return "native replay vs snapshot identical: ten commands, five new nodes, original text, geometry and image renderers; resource=tiles-2.png";
        }
        check(sequence.equals(Arrays.asList(4,3,4,12,3,1)),"commands "+sequence);
        Object saved=snapshot(edited,loader);
        textState(saved,true);ovalState(saved);polygonState(saved,true);
        Bitmap live=artwork(root), fromDisk=artwork(saved);
        check(live.sameAs(fromDisk),"native rendered replay and saved snapshot differ");
        int painted=0;
        for(int y=0;y<600;y++)for(int x=0;x<800;x++)if(live.getPixel(x,y)!=0xffffffff)painted++;
        check(painted>1000,"empty rendered artwork");
        try(OutputStream out=new FileOutputStream(output)){live.compress(Bitmap.CompressFormat.PNG,100,out);}
        return "commands="+sequence+" text=Board 42 size=36 ARGB=FF164E91 at=(72,47); oval=168x82 STROKE 7 ARGB=FF794523; polygon=4 at=(248,144); native replay vs snapshot identical, paintedPixels="+painted;
    }
}
