package local.zy.boardprobe;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.res.AssetManager;
import android.os.Bundle;
import dalvik.system.DexClassLoader;
import java.io.*;
import java.lang.reflect.InvocationTargetException;

/** Give the unmodified page reader its normal Android Application and main looper. */
public class ProbeRun extends Instrumentation {
    private boolean pageWriter, pageReplay, pptWriter, pptGraph, pptViewer, playerVariant, artworkOnly, artworkCreate, artworkImage, newNotebook, artworkVariant, noteBundle, noteRestore;
    private String variantFolder;
    private String paperTimes;
    private String pauseCursor;
    private String cursorDirectory;
    private boolean contentThumbnail, scrollable, ruledPaper, recordCursor, recordCamera, forwardCamera;
    @Override public void onCreate(Bundle args) {
        super.onCreate(args);
        pageWriter = args != null && "true".equals(args.getString("pageWriter"));
        contentThumbnail = args != null && "1".equals(args.getString("contentThumbnail"));
        scrollable = args != null && "1".equals(args.getString("scrollable"));
        ruledPaper = args != null && "1".equals(args.getString("ruledPaper"));
        forwardCamera = args != null && "1".equals(args.getString("forwardCamera"));
        recordCamera = args != null && "1".equals(args.getString("recordCamera"));
        recordCursor = args != null && "1".equals(args.getString("recordCursor"));
        cursorDirectory = args == null ? null : args.getString("cursorDirectory");
        if(cursorDirectory!=null && !cursorDirectory.matches("(?:cursor|camera)-[0-9a-f]{32}"))
            throw new IllegalArgumentException("Invalid replay fixture directory");
        paperTimes = args == null ? null : args.getString("paperTimes");
        pauseCursor = args == null ? null : args.getString("pauseCursor");
        pptWriter = args != null && "true".equals(args.getString("pptWriter"));
        pptGraph = args != null && "true".equals(args.getString("pptGraph"));
        pptViewer = args != null && "true".equals(args.getString("pptViewer"));
        noteRestore = args != null && "true".equals(args.getString("noteRestore"));
        noteBundle = args != null && "true".equals(args.getString("noteBundle"));
        artworkVariant = args != null && "true".equals(args.getString("artworkVariant"));
        pageReplay = args != null && "true".equals(args.getString("pageReplay"));
        newNotebook = args != null && "true".equals(args.getString("newNotebook"));
        artworkCreate = args != null && "true".equals(args.getString("artworkCreate"));
        artworkImage = args != null && "true".equals(args.getString("artworkImage"));
        artworkOnly = args != null && "true".equals(args.getString("artworkOnly"));
        playerVariant = args != null && "true".equals(args.getString("playerVariant"));
        variantFolder = args != null && "true".equals(args.getString("withImages")) ? "image-edit" : "transform-edit";
        start();
    }
    private void copyAsset(String name,File to) throws IOException {
        AssetManager assets=getContext().getAssets();
        String[] entries=assets.list(name);
        if(entries!=null && entries.length>0) {
            to.mkdirs();
            for(String child:entries)copyAsset(name+"/"+child,new File(to,child));
        } else try(InputStream in=assets.open(name); OutputStream out=new FileOutputStream(to)) {
            byte[] buf=new byte[32768]; int n;
            while((n=in.read(buf))!=-1)out.write(buf,0,n);
        }
    }
    @Override public void onStart() {
        if(android.os.Looper.myLooper()==null)android.os.Looper.prepare();
        Bundle result=new Bundle();
        try {
            File dir=getContext().getFilesDir();
            if (pageWriter) {
                File apk=new File(dir,"writer-original.apk");
                copyAsset("mistake.apk",apk);
                DexClassLoader loader=new DexClassLoader(apk.getPath(),getContext().getCodeCacheDir().getPath(),
                    getTargetContext().getApplicationInfo().nativeLibraryDir,getClass().getClassLoader());
                File out=java.nio.file.Files.createTempDirectory(dir.toPath(),"page-writer-").toFile();
                boolean reopen=getContext().getAssets().list("writer-input").length>0;
                if (reopen) copyAsset("writer-input",out);
                if(paperTimes!=null && !paperTimes.isEmpty())
                    PageWriterProbe.playPaper(this,loader,apk,out,paperTimes,pauseCursor,forwardCamera);
                else PageWriterProbe.save(this,loader,apk,out,reopen,contentThumbnail,scrollable,ruledPaper,recordCursor,recordCamera);
                result.putString("saved",out.getName());
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (pptWriter) {
                File deck=new File(dir,"slide-fixture");
                copyAsset("ppt-fixture",deck);
                File apk=new File(dir,"ppt-vendor.apk");
                DexClassLoader loader=new DexClassLoader(apk.getPath(),getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                File out=java.nio.file.Files.createTempDirectory(dir.toPath(),"ppt-writer-").toFile();
                PptRecorderProbe.save(this,loader,apk,new File(deck,"lesson.html"),out);
                result.putString("saved",out.getName());
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (pptGraph) {
                File pages=java.nio.file.Files.createTempDirectory(dir.toPath(),"ppt-pages-").toFile();
                copyAsset("ppt-pages",pages);
                File apk=new File(dir,"ppt-vendor.apk");
                DexClassLoader loader=new DexClassLoader(apk.getPath(),getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                result.putString("graphs",PptGraphProbe.run(this,loader,apk,pages));
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (pptViewer) {
                File deck=new File(dir,"slide-fixture");
                copyAsset("ppt-fixture",deck);
                File apk=new File(dir,"ppt-vendor.apk");
                DexClassLoader loader=new DexClassLoader(apk.getPath(),getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                result.putString("presentation",PptWebViewProbe.run(this,loader,new File(deck,"lesson.html")));
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (playerVariant) {
                copyAsset(variantFolder,new File(dir,variantFolder));
                File apk=new File(dir,"player-variant.apk");
                DexClassLoader variant=new DexClassLoader(apk.getPath(),getContext().getCodeCacheDir().getPath(),
                    null,getClass().getClassLoader());
                final Throwable[] failure={null};
                runOnMainSync(() -> {
                    try { result.putString("player",NativePlayerProbe.run(getTargetContext(),variant,dir,variantFolder,true,apk)); }
                    catch(Throwable error) { failure[0]=error; }
                });
                if (failure[0]!=null) throw failure[0];
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (noteBundle || noteRestore) {
                File sample=java.nio.file.Files.createTempDirectory(dir.toPath(),"bundle-").toFile();
                File lesson=new File(sample,"lesson");
                copyAsset("note-bundle",lesson);
                if(noteBundle && !new File(lesson,"empty-folder").mkdir())throw new IOException("empty folder");
                for(String name:new String[]{"probe.jar","mistake.apk"})copyAsset(name,new File(dir,name));
                DexClassLoader loader=new DexClassLoader(new File(dir,"probe.jar")+":"+new File(dir,"mistake.apk"),getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
                    .invoke(null,(android.app.Application)getTargetContext().getApplicationContext());
                if (noteRestore) {
                    File edited=new File(sample,"editor.zip");copyAsset("edited-note.zip",edited);
                    Object check=loader.loadClass("NoteBundleProbe").getMethod("restore",File.class,File.class,File.class).invoke(null,lesson,edited,sample);
                    result.putString("noteRestore",String.valueOf(check));finish(Activity.RESULT_OK,result);return;
                }
                Object summary=loader.loadClass("NoteBundleProbe").getMethod("pack",File.class).invoke(null,lesson);
                java.nio.file.Files.copy(new File(sample,"lesson_upload.zip").toPath(),new File(dir,"last-note.zip").toPath(),
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                result.putString("note",String.valueOf(summary));
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (artworkVariant) {
                if (cursorDirectory!=null) copyAsset("probe.jar",new File(dir,"probe.jar"));
                else if (pageReplay) for(String name:new String[]{"probe.jar","new-note"}) copyAsset(name,new File(dir,name));
                File apk=new File(dir,"art-variant.apk");
                DexClassLoader loader=new DexClassLoader(new File(dir,"probe.jar")+":"+apk,getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                Object answer=loader.loadClass("ArtworkVariantProbe").getMethod("run",android.app.Application.class,File.class,File.class,File.class,File.class)
                    .invoke(null,getTargetContext().getApplicationContext(),new File(dir,"art-base/lesson/p1"),new File(dir,cursorDirectory!=null?cursorDirectory:pageReplay?"new-note/lesson/p1":"art-edited/lesson/p1"),
                        new File(dir,"art-variant.properties"),new File(dir,"art-variant-result"));
                result.putString("artworkVariant",String.valueOf(answer));
                finish(Activity.RESULT_OK,result);
                return;
            }
            if (newNotebook || pageReplay) {
                for(String name:new String[]{"probe.jar","mistake.apk","new-note"})copyAsset(name,new File(dir,name));
                DexClassLoader loader=new DexClassLoader(new File(dir,"probe.jar")+":"+new File(dir,"mistake.apk"),
                    getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
                loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
                    .invoke(null,getTargetContext().getApplicationContext());
                if (pageReplay) {
                    Object frames=loader.loadClass("PageReplayProbe").getMethod("run",File.class,File.class)
                        .invoke(null,new File(dir,"new-note/lesson/p1"),new File(dir,"page-replay"));
                    result.putString("replay",String.valueOf(frames));finish(Activity.RESULT_OK,result);return;
                }
                Object answer=loader.loadClass("ArtworkCommandProbe").getMethod("newNotebook",File.class)
                    .invoke(null,new File(dir,"new-note/lesson"));
                result.putString("notebook",String.valueOf(answer));finish(Activity.RESULT_OK,result);return;
            }
            if (artworkOnly || artworkCreate || artworkImage) {
                for (String name : new String[]{"probe.jar","mistake.apk","art-base","art-edited"})
                    copyAsset(name,new File(dir,name));
                DexClassLoader loader = new DexClassLoader(new File(dir,"probe.jar")+":"+new File(dir,"mistake.apk"),
                    getContext().getCodeCacheDir().getPath(), null, getClass().getClassLoader());
                loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
                    .invoke(null,(android.app.Application)getTargetContext().getApplicationContext());
                Object answer = loader.loadClass("ArtworkCommandProbe").getMethod("run",File.class,File.class,File.class,String.class)
                    .invoke(null,new File(dir,"art-base/lesson/p1"),new File(dir,"art-edited/lesson/p1"),new File(dir,"art-native.png"),artworkImage ? "image" : artworkCreate ? "create" : "edit");
                result.putString("artwork",String.valueOf(answer));
                finish(Activity.RESULT_OK,result);
                return;
            }
            for(String name:new String[]{"probe.jar","mistake.apk","lesson","simple","recording","browser-edit","transform","transform-edit"})copyAsset(name,new File(dir,name));
            for(String name:new String[]{"illustration","image-recording","image-edit"}) {
                if(getContext().getAssets().list(name).length>0)copyAsset(name,new File(dir,name));
            }
            for(int v=1;v<=5;v++) copyAsset("image-v"+v,new File(dir,"image-v"+v));
            DexClassLoader loader=new DexClassLoader(new File(dir,"probe.jar")+":"+new File(dir,"mistake.apk"),
                getContext().getCodeCacheDir().getPath(),null,getClass().getClassLoader());
            loader.loadClass("com.blankj.utilcode.util.c").getMethod("i",android.app.Application.class)
                .invoke(null,(android.app.Application)getTargetContext().getApplicationContext());
            loader.loadClass("BoardProbe").getMethod("main",String[].class)
                .invoke(null,(Object)new String[]{"page-read",new File(dir,"lesson/p1").getPath()});
            result.putString("page","Verified native router, command, touch source, graph and source index");
            final Throwable[] viewFailure = {null};
            runOnMainSync(() -> {
                try {
                    for(String name:new String[]{"illustration","image-recording","image-edit"}) {
                        if(getContext().getAssets().list(name).length>0)
                            result.putString(name,NativePlayerProbe.run(getTargetContext(),loader,dir,name,true));
                    }
                    for(int v=1;v<=5;v++) {
                        String name="image-v"+v;
                        try {
                            result.putString(name,NativePlayerProbe.run(getTargetContext(),loader,dir,name,true));
                        } catch(InvocationTargetException failure) {
                            Throwable cause=failure.getCause();
                            if(v!=1 || !cause.getClass().getSimpleName().equals("LowVersionException")) throw failure;
                            result.putString(name,cause.toString());
                        }
                    }
                    result.putString("sketchTransforms",NativePlayerProbe.run(getTargetContext(),loader,dir,"transform",false));
                    result.putString("editedTransforms",NativePlayerProbe.run(getTargetContext(),loader,dir,"transform-edit",true));
                    NativeViewProbe.run(getTargetContext(),loader,dir);
                    result.putString("nativePlayer",NativePlayerProbe.run(getTargetContext(),loader,dir,"recording",false));
                    result.putString("editedRecording",NativePlayerProbe.run(getTargetContext(),loader,dir,"browser-edit/recording",true));
                }
                catch(Throwable error) { viewFailure[0]=error; }
            });
            if(viewFailure[0]!=null)throw viewFailure[0];
            result.putString("nativeView","SimpleBoardView rendered the web export and saved 3 paths after touch input");
            finish(Activity.RESULT_OK,result);
        } catch(Throwable error) {
            result.putString("error",android.util.Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,result);
        }
    }
}
