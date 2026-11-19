import android.util.Base64;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import org.json.JSONArray;
import org.json.JSONObject;

/** Run the APK's own protobuf -> ObjectBox entity -> protobuf converters on ART. */
public final class PaperStoreProbe {
    private static Object instance(Class<?> owner) throws Exception {
        for(Field field:owner.getDeclaredFields()) {
            if(Modifier.isStatic(field.getModifiers()) && field.getType()==owner) {
                field.setAccessible(true);
                return field.get(null);
            }
        }
        throw new IllegalStateException("Missing singleton: "+owner);
    }
    private static Object convert(String owner,String name,Class<?> from,Object argument) throws Exception {
        Class<?> converter=Class.forName(owner);
        Method method=converter.getDeclaredMethod(name,from);
        method.setAccessible(true);
        return method.invoke(Modifier.isStatic(method.getModifiers())?null:instance(converter),argument);
    }
    public static void main(String[] args) throws Exception {
        Class<?> wire=Class.forName("com.zykj.board.EzyHeader$BackgroundLineConfig");
        Class<?> entity=Class.forName("com.zykj.blackboard.core.data.dao.BackgroundLineConfigEntity");
        Object parser=wire.getMethod("getParserForType").invoke(instance(wire));
        byte[] raw=Base64.decode(args[4],Base64.DEFAULT);
        Object message=Class.forName("com.google.protobuf.Parser").getMethod("parseFrom",byte[].class)
            .invoke(parser,(Object)raw);
        Object row=convert(args[0],args[1],wire,message);
        ArrayList<Float> values=new ArrayList<>();
        JSONObject result=new JSONObject();
        for(Field field:entity.getDeclaredFields()) {
            if(Modifier.isStatic(field.getModifiers())) continue;
            field.setAccessible(true);
            if(field.getType()==float.class) {
                values.add(field.getFloat(row));
            } else if(field.getType()==int.class) {
                result.put("line_color",field.getInt(row));
            } else if(field.getType().isEnum()) {
                result.put("line_type",((Enum<?>)field.get(row)).ordinal());
            }
        }
        Collections.sort(values);
        result.put("floats",new JSONArray(values));
        if(!args[2].equals("-")) {
            Object restored=convert(args[2],args[3],entity,row);
            byte[] out=(byte[])wire.getMethod("toByteArray").invoke(restored);
            result.put("serialized",Base64.encodeToString(out,Base64.NO_WRAP));
        }
        System.out.println(result);
    }
}
