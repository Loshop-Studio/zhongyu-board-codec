import java.io.FileInputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

/** Read task times from the scheduling implementation packaged in the original APK. */
public final class TimelineProbe {
    static Object call(Object object, String name) throws Exception {
        return object.getClass().getMethod(name).invoke(object);
    }
    static Object emptyListener(Class<?> type) {
        return Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, (p,m,args) -> null);
    }
    public static void main(String[] args) throws Exception {
        if (android.os.Looper.getMainLooper()==null) android.os.Looper.prepareMainLooper();
        Class<?> board=Class.forName("com.zykj.sketch.EzyDrawBoard$DrawBoard");
        Object doc;
        try (FileInputStream input=new FileInputStream(args[0])) {
            doc=board.getMethod("parseFrom",java.io.InputStream.class).invoke(null,input);
        }
        Object records=call(call(doc,"getBoardBody"),"getActionContentList");
        Class<?> listener=Class.forName("com.zykj.sketch.core.listener.EventListener");
        Class<?> callback=Class.forName("r6.c");
        for (int version=1;version<=5;version++) {
            Class<?> parser=Class.forName("com.zykj.sketch.core.version.GraphTaskParseVersion"+version);
            Method parse=parser.getMethod("parse",List.class,listener,callback);
            Object tasks=parse.invoke(parser.getConstructor().newInstance(),records,emptyListener(listener),emptyListener(callback));
            List<String> events=new ArrayList<>(),audio=new ArrayList<>();
            for (Object event:(List<?>)call(tasks,"getGraphTask")) events.add(call(event,"getStartTime").toString());
            for (Object clip:(List<?>)call(tasks,"getAudioTaskList")) audio.add(call(clip,"getFileName")+"@"+call(clip,"getStartTime"));
            System.out.println("Native V"+version+" progress="+call(tasks,"getProgress")+" ms; graph="+events+"; audio="+audio);
        }
    }
}
