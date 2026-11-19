import android.graphics.Paint;
import android.graphics.PointF;
import java.io.File;
import java.io.FileInputStream;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

/** Runs on a disposable ART instance using the original application's board classes. */
public final class BoardProbe {
    private static final String SKETCH = "com.zykj.sketch.EzyDrawBoard$";

    static Object call(Object obj, String name, Object... args) throws Exception {
        Class<?> cls = obj instanceof Class<?> ? (Class<?>) obj : obj.getClass();
        for (Method method : cls.getMethods()) {
            if (!name.equals(method.getName()) || method.getParameterTypes().length != args.length) continue;
            try {
                return method.invoke(obj instanceof Class<?> ? null : obj, args);
            } catch (IllegalArgumentException mismatch) {
                // Generated builders overload the same setter with a message and a builder.
            }
        }
        throw new NoSuchMethodException(cls.getName() + "." + name);
    }
    private static Object builder(String name) throws Exception {
        return call(Class.forName(SKETCH + name), "newBuilder");
    }
    private static Object createAction(String type, String messageName, Object payload) throws Exception {
        Object any = call(Class.forName("com.google.protobuf.Any"), "pack", call(payload,"build"));
        Object event = builder("ActionContent");
        call(event, "setAction", any);
        call(event, "setType", Class.forName(SKETCH+"ActionEnum").getField(type).get(null));
        return call(event, "build");
    }
    private static void writeSketch(File dir) throws Exception {
        Object head=builder("BoardHead");
        call(head,"setVersion",5); call(head,"setWidth",800); call(head,"setHeight",600); call(head,"setType",1);
        Object mode=builder("ActionModeConfig");
        call(mode,"setMode",Class.forName(SKETCH+"ActionModeConfig$Mode").getField("ACTION_WRITING").get(null));
        Object style=builder("ActionGraphConfig$GraphConfig"); call(style,"setColor",0xff286c63);call(style,"setWidth",6f);
        Object config=builder("ActionGraphConfig");call(config,"setConfig",call(style,"build"));
        Object touch=builder("ActionTouchEvent");call(touch,"setStartTime",1000L);
        for(int i=0;i<3;i++) {
            float x=20f+i*60f,y=i==1?120f:50f;
            Object p=builder("ActionTouchEvent$TouchEvent");call(p,"setX",x);call(p,"setY",y);
            call(p,"setAction",i==0?0:i==1?2:1);call(p,"setEventTime",1000L+i*8);call(p,"setPointerCount",1);
            Object prop=builder("ActionTouchEvent$TouchEvent$PointerProperties");call(prop,"setToolType",2);
            Object coord=builder("ActionTouchEvent$TouchEvent$PointerCoords");call(coord,"setX",x);call(coord,"setY",y);
            call(p,"addPointerProperties",call(prop,"build"));call(p,"addPointerCoords",call(coord,"build"));
            call(touch,"addTouchEvent",call(p,"build"));
        }
        Object body=builder("BoardBody");
        call(body,"addActionContent",createAction("ACTION_MODE","ActionModeConfig",mode));
        call(body,"addActionContent",createAction("ACTION_GRAPH","ActionGraphConfig",config));
        call(body,"addActionContent",createAction("ACTION_TOUCH","ActionTouchEvent",touch));
        Object board=builder("DrawBoard");call(board,"setBoardHead",call(head,"build"));call(board,"setBoardBody",call(body,"build"));
        Object io=Class.forName("com.zykj.sketch.utils.ProtoFileUtils").getField("Companion").get(null);
        call(io,"saveProtoFile",dir.toString(),call(board,"build"));
    }
    public static void main(String[] args) throws Exception {
        if(android.os.Looper.getMainLooper()==null)android.os.Looper.prepareMainLooper();
        File file=new File(args[1]);
        if(args[0].equals("sketch-write")) writeSketch(file);
        else if(args[0].equals("page-read")) {
            Object io=Class.forName("com.zykj.blackboard.core.data.SourceLoad").getField("INSTANCE").get(null);
            Object refs=call(io,"getRouter",file.toString());
            Object touchRef=((List<?>)call(refs,"getTouchSourceRecordList")).get(0);
            Object cmdRef=((List<?>)call(refs,"getCommandRecordList")).get(0);
            Object source=call(io,"getTouchRecord",file.toString(),call(touchRef,"getFileName"),call(touchRef,"getValidate"));
            Object commands=call(io,"getCommandRecord",file.toString(),call(cmdRef,"getFileName"),call(cmdRef,"getValidate"));
            try(FileInputStream stream=new FileInputStream(new File(file,"snapshot.bin"))){
                Object page=call(Class.forName("com.zykj.board.EzyPageSnapshot$PageSnapshot"),"parseFrom",stream);
                Object child=((List<?>)call(call(page,"getGraphSnapshot"),"getChildGraphList")).get(0);
                if(!call(child,"getSourceFileName").equals(call(touchRef,"getFileName")))throw new IllegalStateException("Source link mismatch");
                Object info=((List<?>)call(source,"getTouchInfoList")).get((Integer)call(child,"getSourceId"));
                Object command=((List<?>)call(commands,"getCommandInfoList")).get(0);
                Object graph=call(Class.forName("com.zykj.board.EzyCommand$CommandSource$CommandInfo$GraphData"),"parseFrom",call(command,"getData"));
                if(!call(graph,"getGraphId").equals(call(child,"getId")))throw new IllegalStateException("Graph link mismatch");
                System.out.println("page graph="+call(child,"getGraphEnum")+" events="+((List<?>)call(info,"getTouchEventList")).size()+" command="+call(command,"getCommandEnum"));
            }
        } else if(args[0].equals("sketch-read")) {
            try(FileInputStream in=new FileInputStream(file)) {
                Object board=call(Class.forName(SKETCH+"DrawBoard"),"parseFrom",in);
                Object body=call(board,"getBoardBody");
                List<?> events=(List<?>)call(body,"getActionContentList");
                int touches=0, points=0;
                for(Object event:events) if("ACTION_TOUCH".equals(String.valueOf(call(event,"getType")))) {
                    Object value=call(call(event,"getAction"),"unpack",Class.forName(SKETCH+"ActionTouchEvent"));
                    points+=((List<?>)call(value,"getTouchEventList")).size();touches++;
                }
                if(touches==0 || points==0)throw new IllegalStateException("No ink");
                System.out.println("sketch strokes="+touches+" events="+points);
            }
        } else {
            Object io=Class.forName("com.zykj.view.utils.ProtoFileUtils").getField("INSTANCE").get(null);
            if(args[0].equals("simple-write")){
                Paint paint=new Paint();paint.setStrokeWidth(5f);paint.setColor(0xff285a93);
                Object path=Class.forName("com.zykj.view.utils.ProtoPath").getConstructor(Paint.class,List.class)
                    .newInstance(paint,Arrays.asList(new PointF(40,35),new PointF(120,90),new PointF(220,65)));
                call(io,"saveListToFile",Arrays.asList(path),file.toString());
            } else {
                List<?> paths=(List<?>)call(io,"loadDataToList",file.toString());
                if(paths.isEmpty())throw new IllegalStateException("No paths");
                System.out.println("simple strokes="+paths.size()+" first points="+((List<?>)call(paths.get(0),"getPointList")).size());
            }
        }
    }
}
