package local.zy.boardprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.widget.FrameLayout;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import static local.zy.boardprobe.PptWebViewProbe.ui;

/** Save a real V6 recording using the original recorder view, page controller and ObjectBox JNI. */
final class PageWriterProbe {
    private static Method method(Object target,String name,int arity) {
        for(Method m:target.getClass().getMethods())
            if(m.getName().equals(name) && m.getParameterTypes().length==arity) return m;
        throw new IllegalArgumentException(name);
    }
    private static Object callback(Class<?> type,LinkedBlockingQueue<Object> replies) {
        return Proxy.newProxyInstance(type.getClassLoader(),new Class[]{type},(p,m,args)->{
            if(m.getName().equals("invoke"))
                replies.add(args==null || args.length==0 ? Boolean.TRUE : args[0]);
            return null;
        });
    }
    private static Object reply(LinkedBlockingQueue<Object> replies,String stage) throws Exception {
        Object value=replies.poll(15,TimeUnit.SECONDS);
        if(value==null)throw new IllegalStateException("No callback for "+stage);
        if(value instanceof Throwable)throw new IllegalStateException(stage,(Throwable)value);
        return value;
    }
    private static void draw(Instrumentation inst,View v,int[][] points) throws Exception {
        final long down=SystemClock.uptimeMillis();
        for(int i=0;i<points.length;i++) {
            final int[] pt=points[i];
            final int action=i==0?MotionEvent.ACTION_DOWN:i==points.length-1?MotionEvent.ACTION_UP:MotionEvent.ACTION_MOVE;
            ui(inst,()->{
                MotionEvent event=MotionEvent.obtain(down,SystemClock.uptimeMillis(),action,pt[0],pt[1],0);
                try { if(!v.onTouchEvent(event))throw new AssertionError("Unhandled motion"); }
                finally { event.recycle(); }
                return null;
            });
            if(i+1<points.length) SystemClock.sleep(85);
        }
    }
    private static void capture(Object page,File file) throws Exception {
        Bitmap image=(Bitmap)method(page,"screenshot",0).invoke(page);
        writePng(image,file);
    }
    private static void cursor(Instrumentation inst,View view,Object config,File output,int tool,String label,
                               int color,float width,int[][] points) throws Exception {
        ui(inst,()->{
            Method mode=method(config,"setMode",1);
            mode.invoke(config,mode.getParameterTypes()[0].getField("ACTION_CURSOR").get(null));
            method(config,"setCursorColor",1).invoke(config,color);
            method(config,"setCursorWidth",1).invoke(config,width);
            method(config,"setCursorOffset",1).invoke(config,50f);
            return null;
        });
        long down=SystemClock.uptimeMillis();
        for(int i=0;i<points.length;i++){
            final int index=i;
            ui(inst,()->{
                MotionEvent.PointerProperties prop=new MotionEvent.PointerProperties();
                prop.id=0;prop.toolType=tool;
                MotionEvent.PointerCoords pt=new MotionEvent.PointerCoords();
                pt.x=points[index][0];pt.y=points[index][1];pt.pressure=1;
                int action=index==0?0:index==points.length-1?1:2;
                MotionEvent event=MotionEvent.obtain(down,SystemClock.uptimeMillis(),action,1,
                    new MotionEvent.PointerProperties[]{prop},new MotionEvent.PointerCoords[]{pt},0,0,1f,1f,0,0,
                    android.view.InputDevice.SOURCE_TOUCHSCREEN,0);
                try {if(!view.onTouchEvent(event))throw new IllegalStateException("Cursor input");}
                finally {event.recycle();}
                livePaper(view,output,label+"-"+index);
                return null;
            });
            SystemClock.sleep(95);
        }
    }
    private static void sendFingers(View view, long down, int action, int... pairs) {
        int count = pairs.length / 2;
        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[count];
        MotionEvent.PointerCoords[] points = new MotionEvent.PointerCoords[count];
        for (int i = 0; i < count; i++) {
            props[i] = new MotionEvent.PointerProperties();
            props[i].id = i;
            props[i].toolType = MotionEvent.TOOL_TYPE_FINGER;
            points[i] = new MotionEvent.PointerCoords();
            points[i].x = pairs[2*i];
            points[i].y = pairs[2*i+1];
            points[i].pressure = 1;
            points[i].size = 1;
        }
        MotionEvent event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, count,
            props, points, 0, 0, 1, 1, 0, 0, android.view.InputDevice.SOURCE_TOUCHSCREEN, 0);
        try {
            if (!view.onTouchEvent(event)) throw new IllegalStateException("Two-finger event rejected");
        } finally { event.recycle(); }
    }
    private static void pan(Instrumentation inst, View view, File output, String label) throws Exception {
        long down = SystemClock.uptimeMillis();
        int second = 1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT;
        ui(inst, () -> {
            sendFingers(view, down, MotionEvent.ACTION_DOWN, 200, 200);
            sendFingers(view, down, MotionEvent.ACTION_POINTER_DOWN | second, 200, 200, 340, 240);
            return null;
        });
        // The second MOVE changes only the distance between the two fingers.
        int[][] positions = {{188,190,328,230}, {162,184,354,236},
            {133,166,313,202}, {122,151,284,187}};
        for (int i = 0; i < positions.length; i++) {
            final int step = i;
            SystemClock.sleep(105);
            ui(inst, () -> {
                sendFingers(view, down, MotionEvent.ACTION_MOVE, positions[step]);
                livePaper(view, output, label+"-"+step);
                return null;
            });
        }
        SystemClock.sleep(105);
        ui(inst, () -> {
            sendFingers(view, down, MotionEvent.ACTION_POINTER_UP | second, 122,151,284,187);
            sendFingers(view, down, MotionEvent.ACTION_UP, 122,151);
            livePaper(view, output, label+"-up");
            return null;
        });
    }
    private static void writePng(Bitmap image,File file) throws Exception {
        try(FileOutputStream png=new FileOutputStream(file)) {
            if(!image.compress(Bitmap.CompressFormat.PNG,100,png))throw new IllegalStateException("screenshot");
        }
    }
    private static void setPaper(Object page, ClassLoader loader, boolean grid) throws Exception {
        Class<?> lines=loader.loadClass("com.zykj.blackboard.bean.BackgroundLineConfig");
        Class<?> type=loader.loadClass(lines.getName()+"$BackgroundLineType");
        Object style=type.getField(grid?"Interweave":"Horizontal").get(null);
        Object config=lines.getConstructor(int.class,float.class,type,float.class)
            .newInstance(grid?0xff318375:0xff3068a8,grid?40f:32f,style,grid?4f:2f);
        method(page,"setBackgroundColorWithLineConfig",2).invoke(page,grid?0xfffaf4dc:0xfff2f7fd,config);
    }
    private static void livePaper(View view,File output,String name) throws Exception {
        Bitmap image=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);
        view.draw(new android.graphics.Canvas(image));
        writePng(image,new File(output.getParentFile(),output.getName()+"-"+name+".png"));
        image.recycle();
    }
    private static void forwardCursor(Instrumentation inst,Object page,View view,File note,String sample) throws Exception {
        String[] args=sample.split(",");
        int x=Integer.parseInt(args[0]), y=Integer.parseInt(args[1]), color=(int)Long.parseLong(args[2],16);
        Bitmap pixels=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);
        try {
            ui(inst,()->method(page,"start",0).invoke(page));
            final long deadline=SystemClock.elapsedRealtime()+12000;
            boolean paused=false;
            final java.util.LinkedHashSet<String> states=new java.util.LinkedHashSet<>();
            final int[] row=new int[pixels.getWidth()*pixels.getHeight()];
            while(!paused && SystemClock.elapsedRealtime()<deadline){
                paused=ui(inst,()->{
                    pixels.eraseColor(0);
                    view.draw(new android.graphics.Canvas(pixels));
                    if(pixels.getPixel(x,y)!=color){
                        pixels.getPixels(row,0,pixels.getWidth(),0,0,pixels.getWidth(),pixels.getHeight());
                        int minX=pixels.getWidth(),minY=pixels.getHeight(),maxX=-1,maxY=-1;
                        for(int i=0;i<row.length;i++)if(row[i]==color) {
                            int xx=i%pixels.getWidth(),yy=i/pixels.getWidth();
                            minX=Math.min(minX,xx);maxX=Math.max(maxX,xx);minY=Math.min(minY,yy);maxY=Math.max(maxY,yy);
                        }
                        states.add(method(page,"status",0).invoke(page)+" bounds="+minX+","+minY+","+maxX+","+maxY);
                        return false;
                    }
                    method(page,"pause",0).invoke(page);
                    return true;
                });
                if(!paused)SystemClock.sleep(12);
            }
            if(!paused)throw new AssertionError("Cursor never reached requested sample during normal play: "+states);
            ui(inst,()->{livePaper(view,note,"paused");return null;});
            SystemClock.sleep(250);
            ui(inst,()->{livePaper(view,note,"still");method(page,"resume",0).invoke(page);return null;});
            while(!"RECORD_END".equals(method(page,"status",0).invoke(page).toString())){
                if(SystemClock.elapsedRealtime()>=deadline)throw new AssertionError("No playback end");
                SystemClock.sleep(25);
            }
            ui(inst,()->{livePaper(view,note,"ended");return null;});
        } finally {pixels.recycle();}
    }
    private static org.json.JSONObject cameraFrame(Object adapter,long time) throws Exception {
        float[] values=new float[9];
        ((android.graphics.Matrix)method(adapter,"getCameraMatrix",0).invoke(adapter)).getValues(values);
        return new org.json.JSONObject().put("clock",time).put("matrix",new org.json.JSONArray(values));
    }
    private static void playCamera(Instrumentation inst, Object page, View view, File note, String times) throws Exception {
        Object scheduler=method(page,"getCommandThread",0).invoke(page);
        java.lang.reflect.Field clock=scheduler.getClass().getDeclaredField("playTime");
        clock.setAccessible(true);
        long deadline=SystemClock.elapsedRealtime()+12000;
        ui(inst,()->{method(page,"start",0).invoke(page);return null;});
        while(clock.getLong(scheduler)==0) {
            if(SystemClock.elapsedRealtime()>deadline)throw new AssertionError("Camera scheduler did not start");
            SystemClock.sleep(3);
        }
        Object adapter=method(page,"getMatrixAdapter",0).invoke(page);
        org.json.JSONObject observed=new org.json.JSONObject();
        for(String value:times.split(",")){
            long target=Long.parseLong(value);
            while(clock.getLong(scheduler)<target && !"RECORD_END".equals(method(page,"status",0).invoke(page).toString())) {
                if(SystemClock.elapsedRealtime()>deadline)throw new AssertionError("Camera playback timeout "+value);
                SystemClock.sleep(3);
            }
            ui(inst,()->{
                observed.put(value,cameraFrame(adapter,clock.getLong(scheduler)));
                livePaper(view,note,"forward-"+value);
                return null;
            });
        }
        while(!"RECORD_END".equals(method(page,"status",0).invoke(page).toString())){
            if(SystemClock.elapsedRealtime()>deadline)throw new AssertionError("No camera playback end");
            SystemClock.sleep(5);
        }
        ui(inst,()->{
            observed.put("ended",cameraFrame(adapter,clock.getLong(scheduler)));
            livePaper(view,note,"ended");return null;
        });
        SystemClock.sleep(250);
        ui(inst,()->{
            observed.put("settled",cameraFrame(adapter,clock.getLong(scheduler)));
            livePaper(view,note,"settled");return null;
        });
        try(java.io.FileWriter log=new java.io.FileWriter(new File(note.getParent(),note.getName()+"-times.json"))){
            log.write(observed.toString());
        }
    }
    static void playPaper(Instrumentation inst,ClassLoader loader,File apk,File note,String times,String sample,boolean forwardCamera) throws Exception {
        loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
            .invoke(null,inst.getTargetContext().getApplicationContext());
        Activity screen=inst.startActivitySync(new Intent(inst.getTargetContext(),PptWebViewProbe.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        LinkedBlockingQueue<Object> replies=new LinkedBlockingQueue<>();
        try {
            View view=ui(inst,()->{
                Class<?> type=loader.loadClass("com.zykj.blackboard.core.canvas.SketchPlayView");
                View v=(View)type.getConstructor(Context.class,android.util.AttributeSet.class)
                    .newInstance(NativePlayerProbe.resources(screen,apk),null);
                FrameLayout root=new FrameLayout(screen);
                root.addView(v,new FrameLayout.LayoutParams(640,480));
                screen.setContentView(root);
                Method ready=method(v,"ready",1);
                ready.invoke(v,callback(ready.getParameterTypes()[0],replies));
                return v;
            });
            Object control=reply(replies,"player ready");
            Method load=method(control,"loadPath",3);
            load.invoke(control,note.getPath(),callback(load.getParameterTypes()[1],replies),callback(load.getParameterTypes()[2],replies));
            reply(replies,"loadPath");
            ui(inst,()->{
                Method select=method(control,"switchCurrentPlayPage",3);
                return select.invoke(control,0,callback(select.getParameterTypes()[1],replies),callback(select.getParameterTypes()[2],replies));
            });
            reply(replies,"switch page");
            Object page=method(control,"getCurrentPlayPageControl",0).invoke(control);
            if(forwardCamera) {
                playCamera(inst,page,view,note,times);
                return;
            }
            if(sample!=null)forwardCursor(inst,page,view,note,sample);
            for(String text:times.split(",")) {
                long ms=Long.parseLong(text);
                ui(inst,()->{
                    Method seek=method(page,"seekTo",3);
                    return seek.invoke(page,ms,callback(seek.getParameterTypes()[1],replies),callback(seek.getParameterTypes()[2],replies));
                });
                reply(replies,"seek "+ms);
                inst.waitForIdleSync();
                ui(inst,()->{livePaper(view,note,"seek-"+text);return null;});
            }
        } finally { ui(inst,()->{screen.finish();return null;}); }
    }
    static void save(Instrumentation inst,ClassLoader loader,File apk,File output,boolean reopen,boolean contentThumbnail,boolean scrollable,boolean ruledPaper,boolean recordCursor,boolean recordCamera) throws Exception {
        Context target=inst.getTargetContext();
        loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
            .invoke(null,target.getApplicationContext());
        Activity screen=inst.startActivitySync(new Intent(target,PptWebViewProbe.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        Class<?> type=loader.loadClass("com.zykj.blackboard.core.canvas.SketchRecorderView");
        LinkedBlockingQueue<Object> replies=new LinkedBlockingQueue<>();
        try {
            View view=ui(inst,()->{
                Context ctx=NativePlayerProbe.resources(screen,apk);
                View v=(View)type.getConstructor(Context.class,android.util.AttributeSet.class).newInstance(ctx,null);
                FrameLayout root=new FrameLayout(screen);
                root.addView(v,new FrameLayout.LayoutParams(640,480));
                screen.setContentView(root);
                Method ready=method(v,"ready",3);
                ready.invoke(v,output.getPath(),callback(ready.getParameterTypes()[1],replies),
                             callback(ready.getParameterTypes()[2],replies));
                return v;
            });
            Object board=reply(replies,"ready");
            Object page;
            if (reopen) {
                page=NativePlayerProbe.call(board,"getCurrentPage");
                // The original mistake-list helper selects the first listed page and its PNG.
                Class<?> listEntry=loader.loadClass("com.zykj.mistake.utils.h");
                Object entry=listEntry.getConstructor(String.class,String.class).newInstance(output.getPath(),null);
                String preview=(String)method(entry,"d",0).invoke(entry);
                Bitmap decoded=BitmapFactory.decodeFile(preview);
                if(decoded==null) throw new IllegalStateException("List preview missing: "+preview);
                writePng(decoded,new File(output.getParentFile(),output.getName()+"-list.png"));
                decoded.recycle();
                ui(inst,()->{
                    capture(page,new File(output.getParentFile(),output.getName()+"-opened.png"));
                    if(ruledPaper) livePaper(view,output,"grid");
                    Object graph=method(page,"getGraphControl",0).invoke(page);
                    Bitmap content=(Bitmap)method(graph,"contentThumbnail",0).invoke(graph);
                    writePng(content,new File(output.getParentFile(),output.getName()+"-content.png"));
                    content.recycle();
                    return null;
                });
            } else {
                page=ui(inst,()->{
                    if(scrollable || recordCamera) {
                        Object boardConfig=method(board,"getConfig",0).invoke(board);
                        Object move=method(boardConfig,"getMoveActionConfig",0).invoke(boardConfig);
                        method(move,"setMoveActionEnable",1).invoke(move,true);
                        method(move,"setVerticalTranslate",1).invoke(move,true);
                        if(recordCamera) {
                            method(move,"setHorizontalTranslate",1).invoke(move,true);
                            method(move,"setScale",1).invoke(move,true);
                        }
                        method(move,"setMaxHeightTimes",1).invoke(move,3);
                        method(move,"setMaxWidthTimes",1).invoke(move,2);
                    }
                    Method create=method(board,"createPage",2);
                    return create.invoke(board,true,callback(create.getParameterTypes()[1],replies));
                });
                reply(replies,"render");
            }
            Object config=NativePlayerProbe.call(board,"getConfig");
            ui(inst,()->{
                method(config,"setPaintColor",1).invoke(config,reopen?0xff614da8:0xff166f64);
                method(config,"setPaintWidth",1).invoke(config,9f);
                if (!reopen) method(page,"startRecord",1).invoke(page,false);
                return null;
            });
            if (reopen) {
                draw(inst,view,new int[][]{{480,260},{510,285},{525,260},{556,285}});
            } else {
                SystemClock.sleep(170);
                if(ruledPaper) ui(inst,()->{
                    setPaper(page,loader,false);
                    livePaper(view,output,"lines");
                    return null;
                });
                draw(inst,view,new int[][]{{80,74},{120,88},{166,143},{202,92},{232,107}});
                SystemClock.sleep(150);
                if(recordCamera) {
                    ui(inst,()->{
                        setPaper(page,loader,true);
                        method(page,"zoomLevel",3).invoke(page,84f,68f,1.25f);
                        livePaper(view,output,"zoom");
                        return null;
                    });
                    SystemClock.sleep(140);
                    pan(inst,view,output,"pan");
                    SystemClock.sleep(170);
                    ui(inst,()->{
                        Method mode=method(config,"setMode",1);
                        mode.invoke(config,mode.getParameterTypes()[0].getField("ACTION_SEE").get(null));
                        return null;
                    });
                    pan(inst,view,output,"pinch");
                    SystemClock.sleep(145);
                } else if(recordCursor){
                    ui(inst,()->{method(page,"zoomLevel",3).invoke(page,84f,68f,1.25f);return null;});
                    SystemClock.sleep(120);
                    cursor(inst,view,config,output,MotionEvent.TOOL_TYPE_FINGER,"finger",0xffd03177,26f,
                           new int[][]{{160,170},{225,195},{265,230},{300,220}});
                    SystemClock.sleep(110);
                    cursor(inst,view,config,output,MotionEvent.TOOL_TYPE_STYLUS,"stylus",0xff345be0,14f,
                           new int[][]{{340,170},{380,194},{404,228},{430,210}});
                    SystemClock.sleep(120);
                } else {
                    if(ruledPaper) ui(inst,()->{
                        setPaper(page,loader,true);
                        method(page,"zoomLevel",3).invoke(page,84f,68f,1.25f);
                        return null;
                    });
                    if(scrollable) ui(inst,()->{
                        Object camera=method(page,"getMatrixAdapter",0).invoke(page);
                        method(camera,"postCameraTranslate",2).invoke(camera,null,-576f);
                        Object graph=method(page,"getGraphControl",0).invoke(page);
                        method(graph,"reDrawFixView",0).invoke(graph);
                        return null;
                    });
                    ui(inst,()->{method(config,"setPaintColor",1).invoke(config,0xffb25438);return null;});
                    draw(inst,view,new int[][]{{330,220},{365,200},{399,252},{432,232}});
                    SystemClock.sleep(180);
                    if(ruledPaper) ui(inst,()->{livePaper(view,output,"grid");return null;});
                }
                ui(inst,()->{method(page,"stopRecord",0).invoke(page);return null;});
            }
            ui(inst,()->{capture(page,new File(output.getParentFile(),output.getName()+".png"));return null;});
            long limit=SystemClock.elapsedRealtime()+5000;
            while(!(Boolean)method(page,"canSave",0).invoke(page)) {
                if(SystemClock.elapsedRealtime()>limit)throw new IllegalStateException("Page writer busy");
                SystemClock.sleep(25);
            }
            Method save=method(board,"save",4);
            save.invoke(board,false,contentThumbnail,callback(save.getParameterTypes()[2],replies),callback(save.getParameterTypes()[3],replies));
            if(!output.getPath().equals(reply(replies,"save")))throw new AssertionError("Wrong save path");
        } finally { ui(inst,()->{screen.finish();return null;}); }
    }
}
