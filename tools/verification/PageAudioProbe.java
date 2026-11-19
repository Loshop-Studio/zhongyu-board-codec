package local.zy.pageaudio;

import android.media.MediaPlayer;
import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import java.io.File;
import dalvik.system.DexClassLoader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

/** Read the original V6 player's media state after each public seek operation. */
public final class PageAudioProbe extends Instrumentation {
    private Bundle arguments;
    @Override public void onCreate(Bundle extras) {
        super.onCreate(extras);
        arguments = extras;
        start();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            File files = getTargetContext().getFilesDir();
            ClassLoader loader = new DexClassLoader(new File(files, "target.apk").toString(),
                    getTargetContext().getCodeCacheDir().toString(), null, getClass().getClassLoader());
            Class<?> type = loader.loadClass("com.zykj.blackboard.core.play.AudioCommandThread");
            result.putString("seeks", check(type, new File(files, arguments.getString("page")).toString(),
                    arguments.getString("times").split(","), arguments.containsKey("forward"),result));
            finish(Activity.RESULT_OK, result);
        } catch (Throwable e) {
            result.putString("failure", android.util.Log.getStackTraceString(e));
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private static String check(Class<?> type, String path, String[] times, boolean forward, Bundle result) throws Exception {
        StringBuilder rows = new StringBuilder();
        Method seek = null, open = null;
        for (Method method : type.getDeclaredMethods()) {
            if (!Modifier.isPublic(method.getModifiers()) || Modifier.isStatic(method.getModifiers())) continue;
            Class<?>[] params = method.getParameterTypes();
            if (params.length == 2 && params[0] == long.class && params[1].isInterface()) seek = method;
            if (params.length == 1 && params[0] == String.class) open = method;
        }
        Field player = null;
        for (Field field : type.getDeclaredFields()) {
            if (field.getType() == MediaPlayer.class) player = field;
        }
        if (open == null || seek == null || player == null) throw new AssertionError("Original player symbols missing");
        player.setAccessible(true);
        Object thread = type.getConstructor().newInstance();
        open.invoke(thread, path);
        Class<?> callback = seek.getParameterTypes()[1];
        int[] callbacks = {0};
        Object done = Proxy.newProxyInstance(callback.getClassLoader(), new Class<?>[]{callback},
                (proxy, method, values) -> { callbacks[0]++; return null; });
        for (int i = 0; i < times.length; i++) {
            long ms = Long.parseLong(times[i]);
            seek.invoke(thread, ms, done);
            if (callbacks[0] != i + 1) throw new AssertionError("Original seek did not complete");
            MediaPlayer media = (MediaPlayer)player.get(thread);
            int duration = media == null ? -1 : media.getDuration();
            int offset = media == null ? -1 : media.getCurrentPosition();
            if (media != null && media.isPlaying()) throw new AssertionError("Paused seek started audio");
            rows.append(ms).append(',').append(duration).append(',').append(offset).append('|');
        }
        if (forward) {
            Object playing = type.getConstructor().newInstance();
            open.invoke(playing, path);
            for (Method method : type.getDeclaredMethods()) {
                Class<?>[] params = method.getParameterTypes();
                if (Modifier.isPublic(method.getModifiers()) && params.length==1 && params[0]==long.class)
                    method.invoke(playing, 2800L);
            }
            Class<?> status = type.getClassLoader().loadClass("com.zykj.blackboard.enums.PlayStatus");
            for (Method method : type.getSuperclass().getDeclaredMethods()) {
                Class<?>[] params = method.getParameterTypes();
                if (Modifier.isPublic(method.getModifiers()) && params.length==1 && params[0]==status)
                    for (Object value : status.getEnumConstants())
                        if (((Enum<?>)value).name().equals("RECORD_START")) method.invoke(playing,value);
            }
            StringBuilder decoded = new StringBuilder();
            for (int time=0;time<=1936;time+=16) {
                ((Runnable)playing).run();
                if (time==240 || time==1904) {
                    MediaPlayer current = (MediaPlayer)player.get(playing);
                    if (current==null) throw new AssertionError("No media in forward playback at "+time);
                    for (int n=0;n<40 && !current.isPlaying();n++) Thread.sleep(10);
                    if (!current.isPlaying()) throw new AssertionError("Media never started");
                    decoded.append(time).append(',').append(current.getDuration()).append('|');
                }
            }
            result.putString("forward",decoded.toString());
        }
        return rows.toString();
    }
}
