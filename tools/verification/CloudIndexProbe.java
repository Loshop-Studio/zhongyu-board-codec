package local.zy.boardprobe;

import android.app.Application;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import android.util.Log;
import dalvik.system.DexClassLoader;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Offline fixture for the original cloud-note page listing and resource ordering. */
public final class CloudIndexProbe extends Instrumentation {
    private Bundle options;
    private ClassLoader loader;

    @Override public void onCreate(Bundle args) { options = args; start(); }

    private Class<?> type(String name) throws Exception { return loader.loadClass(name); }
    private static File path(File root, String name) { return new File(root, name); }

    private void copyAsset(String source, File dest) throws Exception {
        dest.getParentFile().mkdirs();
        try (InputStream in=getContext().getAssets().open(source);
             OutputStream out=new FileOutputStream(dest)) {
            byte[] buffer=new byte[16384]; int n;
            while ((n=in.read(buffer))!=-1) out.write(buffer,0,n);
        }
    }

    private Object view(String name, Map<String,Object> answers) throws Exception {
        Constructor<?> ctor=type(name).getConstructors()[0];
        Class<?>[] args=ctor.getParameterTypes();
        Object[] values=new Object[args.length];
        for (int i=0;i<args.length;i++) {
            Class<?> iface=args[i];
            if (answers.containsKey(iface.getSimpleName())) {
                values[i]=answers.get(iface.getSimpleName());
                continue;
            }
            values[i]=Proxy.newProxyInstance(loader,new Class<?>[]{iface},(o,m,a)->{
                String key=iface.getSimpleName()+"."+m.getName();
                if (!answers.containsKey(key)) throw new IllegalStateException("Unexpected dependency "+key);
                return answers.get(key);
            });
        }
        return ctor.newInstance(values);
    }

    private JSONObject play(File note, File apk, ClassLoader player, List<?> pages) throws Exception {
        JSONObject result=new JSONObject();
        for (Object page:pages) {
            String name=((File)page).getName();
            if (result.has(name)) continue;
            final Throwable[] failure={null};
            runOnMainSync(()->{
                try { result.put(name,NativePlayerProbe.run(getTargetContext(),player,note,name,true,apk)); }
                catch(Throwable error) { failure[0]=error; }
            });
            if (failure[0]!=null) {
                Throwable cause=failure[0];
                while (cause.getCause()!=null) cause=cause.getCause();
                if (!(cause instanceof NoSuchMethodError) || !cause.toString().contains("makeExtensionsImmutable")) {
                    throw new IllegalStateException("Original playback failed: "+name,failure[0]);
                }
                result.put(name,cause.toString());
            }
        }
        return result;
    }

    private Object database() throws Exception {
        Object builder=type("androidx.room.Room").getMethod("databaseBuilder",Context.class,Class.class,String.class)
            .invoke(null,getTargetContext(),type("com.friday.common.MyDataBase"),"page-order.db");
        return builder.getClass().getMethod("build").invoke(builder);
    }

    private Object await(Object receiver, Method method, Object... arguments) throws Exception {
        Class<?> continuation=type("vc.c");
        Object empty=type("kotlin.coroutines.EmptyCoroutineContext").getField("c").get(null);
        Object[] answer={null};
        java.util.concurrent.CountDownLatch latch=new java.util.concurrent.CountDownLatch(1);
        Object finish=Proxy.newProxyInstance(loader,new Class<?>[]{continuation},(p,m,a)->{
            if (m.getName().equals("getContext")) return empty;
            if (m.getName().equals("resumeWith")) { answer[0]=a[0]; latch.countDown(); return null; }
            throw new IllegalStateException(m.getName());
        });
        Object[] full=Arrays.copyOf(arguments,arguments.length+1);
        full[arguments.length]=finish;
        Object value=method.invoke(receiver,full);
        if (value!=type("wc.a").getMethod("f").invoke(null)) return value;
        if (!latch.await(12,java.util.concurrent.TimeUnit.SECONDS)) throw new IllegalStateException("DAO callback timed out");
        type("kotlin.b").getMethod("b",Object.class).invoke(null,answer[0]);
        return answer[0];
    }

    private JSONObject run(File note, boolean create) throws Exception {
        Object gson=type("com.google.gson.Gson").getConstructor().newInstance();
        Method toJson=gson.getClass().getMethod("toJson",Object.class);
        Class<?> resource=type("com.friday.common.entity.NoteResource");
        File a=path(note,"第一页"), b=path(note,"第2页"), lost=path(note,"missing"), extra=path(note,"unlisted");
        if (create) {
            copyAsset("one.bin",path(a,"actions.bin"));
            copyAsset("two.bin",path(b,"actions.bin"));
            copyAsset("one.bin",path(extra,"actions.bin"));
            List<String> order=Arrays.asList(b.toString(),lost.toString(),a.toString(),b.toString());
            Files.write(path(note,"index.json").toPath(),((String)toJson.invoke(gson,order)).getBytes(StandardCharsets.UTF_8));
            List<Object> assets=new ArrayList<>();
            for (File dir:Arrays.asList(b,a,extra)) {
                File file=path(dir,"actions.bin");
                assets.add(resource.getConstructor(String.class,String.class).newInstance(file.toString(),
                    "https://fixture.invalid/lesson/"+dir.getName()+"/actions.bin"));
            }
            Files.write(path(note,"res.json").toPath(),((String)toJson.invoke(gson,assets)).getBytes(StandardCharsets.UTF_8));
        }
        JSONObject report=new JSONObject();
        Object sync=view("com.friday.document.sync.SyncStateOne",Collections.emptyMap());
        List<?> raw=(List<?>)sync.getClass().getMethod("q",String.class).invoke(sync,note.toString());
        report.put("index",new JSONArray(raw));
        String json=new String(Files.readAllBytes(path(note,"res.json").toPath()),StandardCharsets.UTF_8);
        Object token=type("com.friday.document.service.FileManager$downloadFile$2$a").getDeclaredConstructor().newInstance();
        Type listType=(Type)token.getClass().getMethod("getType").invoke(token);
        List<?> decoded=(List<?>)gson.getClass().getMethod("fromJson",String.class,Type.class).invoke(gson,json,listType);
        JSONArray mappings=new JSONArray();
        for(Object row:decoded) mappings.put(new JSONObject().put("local",resource.getMethod("getLocal").invoke(row))
            .put("service",resource.getMethod("getService").invoke(row)));
        report.put("resources",mappings);
        Class<?> entity=type("com.friday.common.entity.FileEntity");
        Constructor<?> fileCtor=Arrays.stream(entity.getConstructors()).filter(c->c.getParameterTypes().length==19).findFirst().get();
        Object file=fileCtor.newInstance("offline",0L,"Fixture","",note.toString(),"note","","","",0,false,0,false,"",0,"",false,0L,false);
        Map<String,Object> outputs=new HashMap<>();
        outputs.put("FileDao.r",file);
        outputs.put("ResourceDao.V",Collections.emptyList());
        Object vm=view("com.friday.paint.viewmodel.NoteViewModel",outputs);
        List<?> visible=(List<?>)vm.getClass().getMethod("H",String.class,type("vc.c")).invoke(vm,"offline",null);
        JSONArray pages=new JSONArray();
        for(Object f:visible) pages.put(((File)f).getName());
        report.put("editor_pages",pages);
        File original=new File(getTargetContext().getCodeCacheDir(),"original.apk");
        report.put("cloud_sketch",play(note,original,loader,visible));
        File other=new File(getTargetContext().getCodeCacheDir(),"mistake.apk");
        copyAsset("mistake.apk",other);
        ClassLoader sketch=new DexClassLoader(other.toString(),getTargetContext().getCodeCacheDir().toString(),null,getClass().getClassLoader());
        report.put("mistake_sketch",play(note,other,sketch,visible));

        Class<?> ent=type("com.friday.common.entity.ResourceEntity");
        Constructor<?> ctor=Arrays.stream(ent.getConstructors()).filter(c->c.getParameterTypes().length==12).findFirst().get();
        Object order=type("com.friday.common.helper.NotePageOrder").getField("a").get(null);
        File markerFolder=path(note.getParentFile(),"marker-check");
        markerFolder.mkdirs();
        // The fixture runs in an empty test application; bind the rows to the
        // default numeric user chosen by this build for its own DAO query.
        long localUser=((Number)sync.getClass().getMethod("r").invoke(sync)).longValue();
        List<Object> rows=new ArrayList<>();
        for(Object[] spec:new Object[][]{
            {a,"screenshot.png",4,false},{a,"snapshot.bin",8,false},{a,"page_mdb/data.mdb",2,false},
            {b,"screenshot.png",2,false},{b,"snapshot.bin",5,false},{b,"page_mdb/lock.mdb",2,false},
            {lost,"screenshot.png",0,true},{markerFolder,"screenshot.png",0,false}}) {
            File dir=(File)spec[0];
            rows.add(ctor.newInstance(path(dir,(String)spec[1]).toString(),"offline",dir.toString(),spec[2],"","",localUser,0,false,spec[3],null,null));
        }
        Object markers=type("f2.e").getField("a").get(null);
        Method mark=markers.getClass().getMethod("b",File.class);
        Method clear=markers.getClass().getMethod("d",File.class);
        clear.invoke(markers,markerFolder);
        report.put("marker_created",mark.invoke(markers,markerFolder)).put("marker_recreated",mark.invoke(markers,markerFolder));
        Method representatives=order.getClass().getMethod("b",List.class);
        List<?> reps=(List<?>)representatives.invoke(order,rows);
        JSONArray chosen=new JSONArray(),ranks=new JSONArray();
        for(Object row:rows) ranks.put(order.getClass().getMethod("c",ent).invoke(order,row));
        for(Object row:reps) chosen.put(ent.getMethod("getId").invoke(row));
        report.put("resource_ranks",ranks).put("representatives",chosen);
        List<?> previews=(List<?>)order.getClass().getMethod("d",List.class).invoke(order,rows);
        report.put("previews",new JSONArray(previews));
        Object db=database();
        Object dao=type("com.friday.common.MyDataBase").getMethod("u").invoke(db);
        Class<?> resourceDao=type("com.friday.common.dao.ResourceDao"), cont=type("vc.c");
        Method insert=resourceDao.getMethod("E",ent,cont);
        for (Object row:rows) {
            await(dao,insert,row);
        }
        type("androidx.room.RoomDatabase").getMethod("close").invoke(db);
        db=database(); dao=type("com.friday.common.MyDataBase").getMethod("u").invoke(db);
        List<?> persisted=(List<?>)await(dao,resourceDao.getMethod("V",String.class,long.class,cont),"offline",localUser);
        report.put("room_live_count",persisted.size());
        List<?> persistedOrder=(List<?>)representatives.invoke(order,persisted);
        JSONArray ids=new JSONArray();
        for(Object row:persistedOrder) ids.put(ent.getMethod("getId").invoke(row));
        report.put("room_representatives",ids);
        outputs.put("ResourceDao",dao);
        Object realVm=view("com.friday.paint.viewmodel.NoteViewModel",outputs);
        List<?> modern=(List<?>)await(realVm,realVm.getClass().getMethod("H",String.class,cont),"offline");
        JSONArray dbPages=new JSONArray();
        for (Object f:modern) dbPages.put(((File)f).getName());
        report.put("editor_with_room",dbPages);
        type("androidx.room.RoomDatabase").getMethod("close").invoke(db);
        clear.invoke(markers,markerFolder);
        report.put("representatives_after_restore",((List<?>)representatives.invoke(order,rows)).size());
        return report;
    }

    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            if (android.os.Looper.myLooper()==null) android.os.Looper.prepare();
            Context ctx=getTargetContext();
            File apk=new File(ctx.getCodeCacheDir(),"original.apk");
            copyAsset("cloud.apk",apk);
            loader=new DexClassLoader(apk.toString(),ctx.getCodeCacheDir().toString(),null,getClass().getClassLoader());
            type("com.blankj.utilcode.util.Utils").getMethod("init",Application.class).invoke(null,ctx.getApplicationContext());
            File note=new File(ctx.getFilesDir(),"课堂本");
            boolean create=!"read".equals(options.getString("mode"));
            if (!create) {
                File edited=new File(ctx.getCacheDir(),"edited.zip");
                copyAsset("edited.zip",edited);
                type("com.blankj.utilcode.util.ZipUtils").getMethod("unzipFile",File.class,File.class).invoke(null,edited,ctx.getFilesDir());
            }
            JSONObject report=run(note,create);
            Files.write(new File(ctx.getFilesDir(),"report.json").toPath(),report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("result","offline page order read");finish(-1,result);
        } catch(Throwable ex) {
            result.putString("error",Log.getStackTraceString(ex));finish(0,result);
        }
    }
}
