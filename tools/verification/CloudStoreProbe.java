package local.zy.cloudstore;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;
import dalvik.system.DexClassLoader;
import java.io.*;
import java.lang.reflect.InvocationTargetException;

/** Open the cloud-note page store with the APK's original model, cursors and JNI library. */
public final class CloudStoreProbe extends Instrumentation {
    private static final String DAO = "com.zykj.blackboard.core.data.dao.";
    private static Object open(ClassLoader loader, Context context, File dir) throws Exception {
        Object builder = loader.loadClass(DAO + "a").getMethod("y").invoke(null);
        Class<?> type = builder.getClass();
        type.getMethod("a", Object.class).invoke(builder, context.getApplicationContext());
        type.getMethod("f", File.class).invoke(builder, dir);
        return type.getMethod("b").invoke(builder);
    }
    private static Object box(Object store, Class<?> entity) throws Exception {
        return store.getClass().getMethod("g", Class.class).invoke(store, entity);
    }
    private static long put(Object box, Object entity) throws Exception {
        return (Long) box.getClass().getMethod("m", Object.class).invoke(box, entity);
    }
    private static Object get(Object box, long id) throws Exception {
        return box.getClass().getMethod("c", long.class).invoke(box, id);
    }
    private static void copyAssets(Context ctx,String path,File dest) throws IOException {
        String[] children = ctx.getAssets().list(path);
        if (children != null && children.length > 0) {
            dest.mkdirs();
            for (String child : children) copyAssets(ctx,path + "/" + child,new File(dest,child));
        } else {
            try (InputStream in=ctx.getAssets().open(path);OutputStream out=new FileOutputStream(dest)) {
                byte[] data=new byte[16384]; int size;
                while ((size=in.read(data))!=-1) out.write(data,0,size);
            }
        }
    }
    private static String importWebPage(ClassLoader loader,Context ctx) throws Exception {
        File lesson = new File(ctx.getFilesDir(),"lesson");
        copyAssets(ctx,"lesson",lesson);
        // The new note editor takes this conversion path when page_mdb is absent.
        Class<?> manager = loader.loadClass("na.d");
        Object singleton = manager.getField("a").get(null);
        manager.getMethod("h",Context.class,String.class).invoke(singleton,ctx,new File(lesson,"page_mdb").toString());
        Object store = manager.getMethod("f").invoke(singleton);
        try {
            Class<?> source = loader.loadClass("x9.b");
            source.getMethod("C",String.class).invoke(source.getField("a").get(null), lesson.toString());
            StringBuilder result = new StringBuilder();
            for (String name:new String[]{"PageEntity","AudioRecordEntity","AudioInfoEntity","CommandInfoEntity","TouchInfoEntity","TouchEventEntity","TextInfoEntity","GeometryInfoEntity","FileInfoEntity","MatrixInfoEntity","MatrixEventEntity"}) {
                Object b = box(store,loader.loadClass(DAO + name));
                java.util.List<?> values = (java.util.List<?>)b.getClass().getMethod("e").invoke(b);
                result.append(name).append("=").append(values.size()).append(" ");
            }
            // Serialize imported recording rows with the APK's SourceSave.saveAudio.
            Class<?> audioRecord = loader.loadClass(DAO + "AudioRecordEntity");
            Object records = box(store,audioRecord);
            java.util.List<?> audioRows = (java.util.List<?>)records.getClass().getMethod("e").invoke(records);
            if (!audioRows.isEmpty()) {
                File output = new File(ctx.getFilesDir(),"audio-rewrite");
                output.mkdirs();
                Class<?> writer = loader.loadClass("x9.c");
                for (Object row : audioRows) {
                    File folder = new File(output,audioRecord.getMethod("c").invoke(row).toString());
                    folder.mkdirs();
                    writer.getMethod("d",String.class,audioRecord)
                            .invoke(writer.getField("a").get(null),folder.toString(),row);
                }
            }
            return result.toString().trim();
        } finally { store.getClass().getMethod("close").invoke(store); }
    }
    private boolean relationFixture;
    private static Object ensureSecond(Object store, Class<?> type) throws Exception {
        Object b=box(store,type);
        Object second=get(b,2L);
        if(second!=null)return second;
        Object item=type.getConstructor().newInstance();
        long id=put(b,item);
        if(id!=2)throw new AssertionError("Unexpected synthetic ID "+type+" "+id);
        return item;
    }
    @SuppressWarnings("unchecked")
    private static int toMany(Object store,ClassLoader loader,Context ctx,boolean write) throws Exception {
        int pairs=0;
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(ctx.getAssets().open("relations.tsv"),"UTF-8"))){
            String line;
            while((line=reader.readLine())!=null){
                String[] spec=line.split("\t");
                Class<?> parent=loader.loadClass(DAO+spec[0]),child=loader.loadClass(DAO+spec[2]);
                Object parents=box(store,parent), children=box(store,child);
                if(write){ensureSecond(store,parent);ensureSecond(store,child);}
                for(long source=1;source<=2;source++){
                    Object owner=get(parents,source);
                    java.util.List<Object> targets=(java.util.List<Object>)parent.getField(spec[1]).get(owner);
                    if(write){
                        for(long j=source;j<=2;j++) targets.add(get(children,j));
                        put(parents,owner);
                    } else {
                        java.util.List<Long> ids=new java.util.ArrayList<>();
                        java.lang.reflect.Field id=child.getDeclaredField("id");id.setAccessible(true);
                        for(Object target:targets)ids.add(id.getLong(target));
                        java.util.Collections.sort(ids);
                        java.util.List<Long> want=source==1?java.util.Arrays.asList(1L,2L):java.util.Arrays.asList(2L);
                        if(!want.equals(ids))throw new AssertionError(spec[0]+"."+spec[1]+" "+source+" -> "+ids);
                        pairs+=ids.size();
                    }
                }
            }
        }
        return pairs;
    }
    // Open an exported MDB directly and materialize its original stroke with
    // the APK's ObjectBox cursor, ToMany relation and native resource adapter.
    private void readEditedInk(ClassLoader loader, Context ctx, Bundle result) throws Exception {
        File dir = new File(ctx.getCacheDir(), "ink-" + System.nanoTime());
        if (!dir.mkdir()) throw new IOException("Could not create snapshot directory");
        copyAssets(ctx, "ink.mdb", new File(dir, "data.mdb"));
        Class<?> manager = loader.loadClass("na.d");
        Object singleton = manager.getField("a").get(null);
        manager.getMethod("h", Context.class, String.class).invoke(singleton, ctx, dir.toString());
        Object store = manager.getMethod("f").invoke(singleton);
        try {
            Class<?> record = loader.loadClass(DAO + "TouchRecordEntity");
            Object row = get(box(store, record), 1L);
            String source = (String)record.getMethod("a").invoke(row);
            Class<?> reader = loader.loadClass("ga.c");
            Object ink = reader.getMethod("a", String.class, int.class)
                .invoke(reader.getConstructor().newInstance(), source, 0);
            result.putString("inkSource", source);
            Object paint = ink.getClass().getMethod("n").invoke(ink);
            result.putString("inkColor", paint.getClass().getMethod("getColor").invoke(paint).toString());
            result.putString("inkWidth", paint.getClass().getMethod("getWidth").invoke(paint).toString());
            java.util.List<?> points = (java.util.List<?>)ink.getClass().getMethod("getTouchEventList").invoke(ink);
            org.json.JSONArray samples = new org.json.JSONArray();
            for (Object point : points) {
                Class<?> type = point.getClass();
                samples.put(new org.json.JSONArray().put(type.getMethod("getX").invoke(point))
                    .put(type.getMethod("getY").invoke(point)).put(type.getMethod("getEventTime").invoke(point)));
            }
            result.putString("inkPoints", samples.toString());
        } finally { store.getClass().getMethod("close").invoke(store); }
    }
    @Override public void onCreate(Bundle args) { super.onCreate(args); relationFixture=args!=null && "1".equals(args.getString("relations")); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            if (android.os.Looper.myLooper()==null) android.os.Looper.prepare();
            Context ctx = getTargetContext();
            File apk = new File(ctx.getFilesDir(), "cloud.apk");
            try (InputStream in = ctx.getAssets().open("cloud.apk"); OutputStream out = new FileOutputStream(apk)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            }
            ClassLoader loader = new DexClassLoader(apk.toString(), ctx.getCodeCacheDir().toString(),
                    ctx.getApplicationInfo().nativeLibraryDir, getClass().getClassLoader());
            loader.loadClass("com.blankj.utilcode.util.Utils").getMethod("init", android.app.Application.class)
                    .invoke(null, ctx.getApplicationContext());
            if (java.util.Arrays.asList(ctx.getAssets().list("")).contains("ink.mdb")) {
                readEditedInk(loader, ctx, result);
                finish(Activity.RESULT_OK, result);
                return;
            }
            File dir = new File(ctx.getFilesDir(), "page_mdb");
            Class<?> page = loader.loadClass(DAO + "PageEntity"), text = loader.loadClass(DAO + "TextInfoEntity");
            java.util.List<String> types = new java.util.ArrayList<>();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(ctx.getAssets().open("entities.txt"), "UTF-8"))) {
                String line;
                while ((line = reader.readLine()) != null) types.add(line);
            }
            Object store = open(loader, ctx, dir);
            long pageId, textId;
            try {
                for (String name : types) {
                    if (name.equals("PageEntity") || name.equals("TextInfoEntity")) continue;
                    Class<?> type = loader.loadClass(DAO + name);
                    Object item = type.getConstructor().newInstance();
                    if (name.equals("AudioInfoEntity") || name.equals("CommandInfoEntity")) {
                        java.lang.reflect.Field payload = type.getDeclaredField("data");
                        payload.setAccessible(true);
                        payload.set(item, new byte[]{1, 35, (byte)0xff, 0});
                    }
                    put(box(store,type),item);
                }
                Object first = page.getConstructor(long.class, String.class, boolean.class, String.class, int.class)
                        .newInstance(0L, "p-local", true, "1_command.bin", 7);
                Object label = text.getConstructor(long.class, float.class, int.class, float.class, int.class, String.class)
                        .newInstance(0L, 18f, 0xff112233, 2f, 1, "本地画板样本");
                Object header = page.getField("headerEntity").get(first);
                header.getClass().getMethod("setTargetId", long.class).invoke(header, 1L);
                pageId = put(box(store,page), first);
                textId = put(box(store,text), label);
                if(relationFixture)toMany(store,loader,ctx,true);
            } finally { store.getClass().getMethod("close").invoke(store); }
            store = open(loader, ctx, dir);
            try {
                Object first = get(box(store,page),pageId), label = get(box(store,text),textId);
                String pageData = first.toString();
                String textData = (String)text.getMethod("b").invoke(label);
                if (!pageData.contains("p-local") || !pageData.contains("commandIndex=7") || !textData.equals("本地画板样本")) {
                    throw new AssertionError(pageData + " / " + textData);
                }
                for (String name : types) {
                    Class<?> type = loader.loadClass(DAO + name);
                    if (get(box(store,type),1L) == null) throw new AssertionError(name);
                }
                if(relationFixture)result.putString("reopenedRelationPairs",String.valueOf(toMany(store,loader,ctx,false)));
                result.putInt("reopenedEntityTypes",types.size());
                result.putString("persisted", pageData + " textId=" + textId + " content=" + textData);
            } finally { store.getClass().getMethod("close").invoke(store); }
            result.putString("webPageImport",importWebPage(loader,ctx));
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            while (error instanceof InvocationTargetException) error=error.getCause();
            result.putString("error",android.util.Log.getStackTraceString(error));
            finish(Activity.RESULT_CANCELED, result);
        }
    }
}
