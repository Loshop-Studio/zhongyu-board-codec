import android.os.Handler;
import android.os.Looper;
import android.os.Messenger;
import java.io.File;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Use the original note enumerator, manifest model and ZIP writer. The callback
 * maps local filenames to synthetic names in memory and performs no transport. */
public final class NoteBundleProbe {
    private static Object continuation(String suffix,Class<?> manager,Object owner) throws Exception {
        Class<?> continuation=Class.forName("h6.c");
        Object empty=Class.forName("kotlin.coroutines.EmptyCoroutineContext").getField("INSTANCE").get(null);
        Object completion=Proxy.newProxyInstance(continuation.getClassLoader(),new Class<?>[]{continuation},(p,m,a)->{
            if(m.getName().equals("getContext"))return empty;
            throw new IllegalStateException(m.getName());
        });
        Constructor<?> ctor=Class.forName("com.zykj.mistake.utils.NoteDownloadUtils$"+suffix+"$1").getDeclaredConstructor(manager,continuation);
        ctor.setAccessible(true);
        return ctor.newInstance(owner,completion);
    }

    public static String pack(File sample) throws Exception {
        if(Looper.myLooper()==null) Looper.prepare();
        File dir=sample.getCanonicalFile();
        String prefix="https://note.invalid/local-fixture";
        Class<?> manager=Class.forName("com.zykj.mistake.utils.j");
        Object owner=manager.getField("a").get(null);
        List<Object> manifest=new ArrayList<>();
        List<String> previews=new ArrayList<>();
        Class<?> callback=Class.forName("r6.f");
        Object localNames=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(p,m,a)->{
            if(!m.getName().equals("invoke"))throw new IllegalStateException(m.getName());
            String dest=(String)a[1];
            String relative=dir.toPath().relativize(new File((String)a[0]).toPath()).toString();
            if(!dest.equals(prefix+"/"+relative))throw new IllegalStateException(dest+" "+relative);
            return dest;
        });
        Object caller=continuation("uploadFile",manager,owner);
        for(Method m:manager.getMethods()) if(m.getName().equals("c") && m.getParameterTypes().length==7)
            m.invoke(owner,dir,manifest,previews,dir.toString(),prefix,localNames,caller);
        if(manifest.isEmpty() || previews.size()!=2)throw new IllegalStateException("manifest="+manifest.size()+" previews="+previews);
        Object gson=Class.forName("com.blankj.utilcode.util.f").getMethod("a").invoke(null);
        String json=(String)gson.getClass().getMethod("f",Object.class).invoke(gson,manifest);
        Files.write(new File(dir,"fileList.json").toPath(),json.getBytes(StandardCharsets.UTF_8));
        Messenger events=new Messenger(new Handler(Looper.myLooper()));
        Class<?> pack=Class.forName("com.zykj.mistake.service.UploadIntentService",false,NoteBundleProbe.class.getClassLoader());
        String archive=(String)pack.getMethod("c",String.class,Messenger.class).invoke(null,dir.toString(),events);
        if(!new File(archive).isFile())throw new IllegalStateException(archive);
        return "entries="+manifest.size()+" previews="+previews.size()+" ZIP="+new File(archive).getName();
    }

    private static List<String> retrieve(File reference, File zip, File dest, boolean asZip) throws Exception {
        final String prefix="https://note.invalid/local-fixture/";
        Class<?> manager=Class.forName("com.zykj.mistake.utils.j");
        Object owner=manager.getField("a").get(null);
        Class<?> callback=Class.forName("r6.f");
        List<String> requests=new ArrayList<>();
        Object fetch=Proxy.newProxyInstance(callback.getClassLoader(),new Class<?>[]{callback},(p,m,a)->{
            if(!m.getName().equals("invoke"))throw new IllegalStateException(m.getName());
            String url=(String)a[0];
            if(!url.startsWith(prefix))throw new IllegalStateException(url);
            String name=url.substring(prefix.length());
            File single=asZip?zip:new File(reference,name);
            File target=new File((String)a[1]);
            if(!asZip && !single.getCanonicalFile().toPath().startsWith(reference.getCanonicalFile().toPath()))
                throw new IllegalStateException("Unrecognized test input");
            if(!target.getCanonicalFile().toPath().startsWith(dest.getParentFile().getCanonicalFile().toPath()))
                throw new IllegalStateException("Unexpected test destination");
            target.getParentFile().mkdirs();
            Files.copy(single.toPath(),target.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            requests.add(name);
            return target.getAbsolutePath();
        });
        dest.mkdirs();
        Method entry=manager.getMethod("a",String.class,String.class,callback,Class.forName("kotlin.coroutines.jvm.internal.ContinuationImpl"));
        Object result=entry.invoke(owner,prefix+(asZip?"folder-note.zip":"fileList.json"),dest.getAbsolutePath(),fetch,
                                  continuation("downloadNote",manager,owner));
        if(!dest.getAbsolutePath().equals(result))throw new IllegalStateException("Native loader result "+result);
        Collections.sort(requests);
        return requests;
    }
    public static String restore(File reference,File zip,File work) throws Exception {
        File fromManifest=new File(work,"manifest"),fromZip=new File(work,"zip");
        List<String> first=retrieve(reference,zip,fromManifest,false);
        if(new HashSet<>(first).size()!=first.size())throw new IllegalStateException("duplicate first-pass request");
        if(new File(fromManifest,"fileList.json").exists())throw new IllegalStateException("unexpected retained transfer list");
        for(String name:first) {
            if(name.equals("fileList.json"))continue;
            if(!Arrays.equals(Files.readAllBytes(new File(reference,name).toPath()),
                              Files.readAllBytes(new File(fromManifest,name).toPath())))
                throw new IllegalStateException("manifest restore differs at "+name);
        }
        List<String> cached=retrieve(reference,zip,fromManifest,false);
        Set<String> expected=new HashSet<>(Arrays.asList("fileList.json","screenshot.png","res/image/tiles.png"));
        if(first.size()!=18 || !new HashSet<>(cached).equals(expected))throw new IllegalStateException("initial="+first+" cached="+cached);
        File snapshot=new File(fromManifest,"p1/snapshot.bin");
        Files.write(snapshot.toPath(),new byte[]{1});
        List<String> repaired=retrieve(reference,zip,fromManifest,false);
        expected.add("p1/snapshot.bin");
        if(!new HashSet<>(repaired).equals(expected) || !Arrays.equals(Files.readAllBytes(snapshot.toPath()),Files.readAllBytes(new File(reference,"p1/snapshot.bin").toPath())))throw new IllegalStateException("refresh "+repaired);
        List<String> unpack=retrieve(reference,zip,fromZip,true);
        if(unpack.size()!=1)throw new IllegalStateException("ZIP fetch "+unpack);
        int count=0;
        try(java.util.zip.ZipFile input=new java.util.zip.ZipFile(zip)) {
            Enumeration<? extends java.util.zip.ZipEntry> entries=input.entries();
            byte[] buffer=new byte[8192];
            while(entries.hasMoreElements()) {
                java.util.zip.ZipEntry e=entries.nextElement();
                if(e.isDirectory())continue;
                try(java.io.InputStream in=input.getInputStream(e)) {
                    java.io.ByteArrayOutputStream data=new java.io.ByteArrayOutputStream();int n;
                    while((n=in.read(buffer))!=-1)data.write(buffer,0,n);
                    if(!Arrays.equals(data.toByteArray(),Files.readAllBytes(new File(fromZip,e.getName()).toPath())))
                        throw new IllegalStateException("ZIP differs at "+e.getName());
                    count++;
                }
            }
        }
        File page=new File(fromZip,"p1");
        Object loader=ArtworkCommandProbe.make(ArtworkCommandProbe.CORE+"loader.CacheSourceLoader");
        ArtworkCommandProbe.call(loader,"initPath",page.getPath());
        Object root=ArtworkCommandProbe.snapshot(page,loader);
        Class<?> strokeType=Class.forName(ArtworkCommandProbe.CORE+"graph.stroke.StrokeGraph");
        List<Integer> painted=new ArrayList<>();
        for(Object child:(List<?>)ArtworkCommandProbe.call(root,"getChildGraph")) {
            if(!strokeType.isInstance(child))continue;
            android.graphics.Bitmap bitmap=android.graphics.Bitmap.createBitmap(800,600,android.graphics.Bitmap.Config.ARGB_8888);
            ArtworkCommandProbe.call(child,"render",new android.graphics.Canvas(bitmap),new android.graphics.Matrix());
            int total=0;
            for(int y=0;y<bitmap.getHeight();y++)for(int x=0;x<bitmap.getWidth();x++) {
                if((bitmap.getPixel(x,y)>>>24)!=0)total++;
            }
            bitmap.recycle();
            if(total==0)throw new IllegalStateException("Restored stroke has no pixels");
            painted.add(total);
        }
        if(painted.size()!=2)throw new IllegalStateException("Expected two strokes on the restored page");
        return "manifest initial="+first.size()+" cached="+cached+" repaired="+repaired+
            "; 17 manifest files equal, temporary manifest removed; Flutter ZIP callbacks="+unpack.size()+" identical files="+count+" native stroke pixels="+painted;
    }
}
