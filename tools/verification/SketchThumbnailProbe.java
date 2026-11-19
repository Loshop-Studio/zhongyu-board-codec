package local.zy.boardprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;
import dalvik.system.DexClassLoader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

import static local.zy.boardprobe.PptWebViewProbe.ui;

/** Exercise the original JPEG writer, recorder reload and Cloud Note sidebar binding. */
public final class SketchThumbnailProbe extends Instrumentation {
    private Bundle options;
    @Override public void onCreate(Bundle b) { options=b; start(); }

    private File installAsset(String name) throws Exception {
        File file=new File(getTargetContext().getCodeCacheDir(),name);
        try(InputStream in=getContext().getAssets().open(name)){
            Files.copy(in,file.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
        return file;
    }
    private ClassLoader loader(File apk) {
        return new DexClassLoader(apk.toString(),getTargetContext().getCodeCacheDir().toString(),null,getClass().getClassLoader());
    }
    private static void png(Bitmap pixels,File path) throws Exception {
        try(FileOutputStream out=new FileOutputStream(path)){
            if(!pixels.compress(Bitmap.CompressFormat.PNG,100,out)) throw new AssertionError("PNG");
        }
    }
    private static Object callback(Class<?> type, CountDownLatch event){
        return Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(p,m,a)->{
            if (m.getName().equals("invoke") && event!=null && a!=null && a[0]!=null) event.countDown();
            return null;
        });
    }
    private static void await(CountDownLatch event,String name) throws Exception {
        if(!event.await(15,TimeUnit.SECONDS)) throw new AssertionError("Missing callback: "+name);
    }
    private static Method method(Object receiver,String name,int arity) throws Exception {
        for(Method m:receiver.getClass().getMethods()){
            if(m.getName().equals(name) && m.getParameterTypes().length==arity) return m;
        }
        throw new NoSuchMethodException(name);
    }
    private void bindSidebar(Activity screen,File jpg,File result,File apk) throws Exception {
        ClassLoader cloud=loader(apk);
        ImageView image=ui(this,()->{
            Context c=NativePlayerProbe.resources(screen,apk);
            FrameLayout layout=new FrameLayout(c);
            Class<?> ids=cloud.loadClass("com.friday.paint.R$id");
            ImageView iv=new ImageView(c);
            iv.setId(ids.getField("iv_thumbnail").getInt(null));
            layout.addView(iv,new FrameLayout.LayoutParams(640,480));
            TextView number=new TextView(c);
            number.setId(ids.getField("tv_page_num").getInt(null));
            number.setVisibility(View.INVISIBLE);
            layout.addView(number);
            ImageView inClass=new ImageView(c);
            inClass.setId(ids.getField("iv_in_class").getInt(null));
            layout.addView(inClass);
            screen.setContentView(layout);
            Class<?> rv=cloud.loadClass("androidx.recyclerview.widget.RecyclerView");
            Object adapter=cloud.loadClass("com.friday.paint.adapter.ThumbnailListAdapter").getConstructor().newInstance();
            adapter.getClass().getMethod("onAttachedToRecyclerView",rv).invoke(adapter,rv.getConstructor(Context.class).newInstance(c));
            Class<?> holder=cloud.loadClass("com.chad.library.adapter.base.viewholder.BaseViewHolder");
            Class<?> entity=cloud.loadClass("com.friday.paint.model.NoteListEntity");
            Object item=entity.getConstructor(String.class,boolean.class,boolean.class,String.class).newInstance(jpg.toString(),true,false,jpg.getParent());
            adapter.getClass().getMethod("convert",holder,entity).invoke(adapter,holder.getConstructor(View.class).newInstance(layout),item);
            return iv;
        });
        for(int i=0;i<80;i++) {
            if(ui(this,()->{
                Drawable imageDrawable=image.getDrawable();
                if(imageDrawable==null || imageDrawable.getIntrinsicWidth()<=0) return false;
                // Coil may supply a GPU-only bitmap. Copy the exact pixels
                // attached by the original adapter before writing evidence.
                Bitmap pixels=((android.graphics.drawable.BitmapDrawable)imageDrawable).getBitmap();
                png(pixels.copy(Bitmap.Config.ARGB_8888,false),result);
                return true;
            })) return;
            SystemClock.sleep(100);
        }
        throw new AssertionError("Cloud thumbnail adapter did not publish a bitmap");
    }
    private void verify(boolean create) throws Exception {
        Context ctx=getTargetContext();
        File dir=new File(ctx.getFilesDir(),"note"); dir.mkdirs();
        File apk=installAsset("reader.apk"), cloud=installAsset("cloud.apk");
        ClassLoader classes=loader(apk);
        Activity screen=startActivitySync(new Intent(ctx,PptWebViewProbe.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            Class<?> type=classes.loadClass("com.zykj.sketch.core.record.SketchRecorderView");
            View recorder=ui(this,()->{
                Context c=NativePlayerProbe.resources(screen,apk);
                View v=(View)type.getConstructor(Context.class,android.util.AttributeSet.class).newInstance(c,null);
                FrameLayout layout=new FrameLayout(screen);
                layout.addView(v,new FrameLayout.LayoutParams(640,480));screen.setContentView(layout);
                return v;
            });
            waitForIdleSync();
            Object control=NativePlayerProbe.field(recorder,"recordControl");
            Object config=NativePlayerProbe.field(recorder,"sketchConfig");
            ui(this,()->{config.getClass().getMethod("setSourcePath",String.class).invoke(config,dir.toString());return null;});
            if(create){
                CountDownLatch imageReady=new CountDownLatch(1);
                ui(this,()->{
                    type.getMethod("setSketchBackground",int.class).invoke(recorder,0xfff8f3e4);
                    Method add=type.getMethod("addImage",Bitmap.class,String.class,int.class,int.class,
                        method(recorder,"addPPT",2).getParameterTypes()[1],method(recorder,"addPPT",2).getParameterTypes()[1]);
                    Class<?> fn=add.getParameterTypes()[4];
                    Bitmap bitmap=Bitmap.createBitmap(88,64,Bitmap.Config.ARGB_8888);
                    Canvas canvas=new Canvas(bitmap);canvas.drawColor(0xff087fa5);
                    Paint paint=new Paint();paint.setColor(0xffeda72f);canvas.drawRect(10,8,60,46,paint);
                    add.invoke(recorder,bitmap,"diagram",5,23,callback(fn,imageReady),callback(fn,null));
                    return null;
                });
                await(imageReady,"image");
                ui(this,()->{
                    Class<?> mode=classes.loadClass("com.zykj.sketch.core.data.Mode");
                    type.getMethod("setMode",mode).invoke(recorder,mode.getField("ACTION_WRITING").get(null));
                    Class<?> pen=classes.loadClass("com.zykj.sketch.core.config.GraphConfig");
                    type.getMethod("setGraphConfig",pen).invoke(recorder,pen.getConstructor(float.class,int.class).newInstance(9f,0xff98324c));
                    long start=SystemClock.uptimeMillis();
                    int[][] points={{0,15,100},{2,90,120},{2,180,100},{2,230,125},{1,260,115}};
                    for(int i=0;i<points.length;i++){
                        int[] p=points[i];MotionEvent e=MotionEvent.obtain(start,start+i*10,p[0],p[1],p[2],0);
                        try{control.getClass().getMethod("onTouchAdapterEvent",MotionEvent.class).invoke(control,e);}finally{e.recycle();}
                    }
                    type.getMethod("setDrawArea",RectF.class).invoke(recorder,new RectF(50,45,600,445));
                    return null;
                });
                CountDownLatch saved=new CountDownLatch(1);
                ui(this,()->{
                    Method save=method(recorder,"getRecordPath",1);
                    save.invoke(recorder,callback(save.getParameterTypes()[0],saved));
                    return null;
                });
                await(saved,"getRecordPath");
            } else {
                CountDownLatch opened=new CountDownLatch(1);
                try {
                    ui(this,()->{
                        Method load=method(control,"loadData",3);
                        load.invoke(control,dir.toString(),callback(load.getParameterTypes()[1],null),callback(load.getParameterTypes()[2],opened));
                        return null;
                    });
                    await(opened,"RecordControl.loadData");
                } catch (Exception ex) {
                    Throwable cause=ex;
                    while(cause.getCause()!=null) cause=cause.getCause();
                    if(!"true".equals(options.getString("cloudReader")) || !(cause instanceof NoSuchMethodError) ||
                            !cause.toString().contains("makeExtensionsImmutable")) throw ex;
                    JSONObject report=new JSONObject().put("load_error",cause.toString());
                    Files.write(new File(ctx.getFilesDir(),"report.json").toPath(),report.toString().getBytes("UTF-8"));
                    bindSidebar(screen,new File(dir,"thumbnail.jpg"),new File(ctx.getFilesDir(),"sidebar.png"),cloud);
                    return;
                }
            }
            ui(this,()->{
                Bitmap output=(Bitmap)type.getMethod("thumbnail").invoke(recorder);
                png(output,new File(ctx.getFilesDir(),"recorder.png"));
                Object codec=classes.loadClass("com.zykj.sketch.utils.FileUtils").getField("Companion").get(null);
                codec.getClass().getMethod("saveBitmap2SDCard",Bitmap.class,String.class).invoke(codec,output,new File(ctx.getFilesDir(),"recorder.jpg").toString());
                Bitmap alpha=Bitmap.createBitmap(128,32,Bitmap.Config.ARGB_8888);
                Canvas alphaCanvas=new Canvas(alpha);
                Paint swatch=new Paint();
                for(int i=0;i<4;i++){
                    swatch.setColor(android.graphics.Color.argb(new int[]{0,64,128,255}[i],192,80,32));
                    alphaCanvas.drawRect(i*32,0,(i+1)*32,32,swatch);
                }
                codec.getClass().getMethod("saveBitmap2SDCard",Bitmap.class,String.class).invoke(codec,alpha,new File(ctx.getFilesDir(),"alpha.jpg").toString());
                Object graph=NativePlayerProbe.field(control,"graphControl");
                Object root=NativePlayerProbe.call(graph,"getRootGraph");
                JSONObject report=new JSONObject().put("width",output.getWidth()).put("height",output.getHeight())
                    .put("strokes",root.getClass().getMethod("childTypeNumber",String.class).invoke(root,"com.zykj.sketch.core.graph.StrokeGraph"))
                    .put("images",root.getClass().getMethod("childTypeNumber",String.class).invoke(root,"com.zykj.sketch.core.graph.ImageGraph"));
                Files.write(new File(ctx.getFilesDir(),"report.json").toPath(),report.toString().getBytes("UTF-8"));
                NativePlayerProbe.call(control,"onDestroy");
                return null;
            });
            bindSidebar(screen,new File(dir,"thumbnail.jpg"),new File(ctx.getFilesDir(),"sidebar.png"),cloud);
        }finally{ui(this,()->{screen.finish();return null;});}
    }
    @Override public void onStart(){
        Bundle out=new Bundle();
        try{verify("create".equals(options.getString("mode")));out.putString("stream","Original recorder and sidebar rendered");finish(-1,out);}
        catch(Throwable ex){out.putString("stream",Log.getStackTraceString(ex));finish(0,out);}
    }
}
