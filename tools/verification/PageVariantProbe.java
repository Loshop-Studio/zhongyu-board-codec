import java.io.*;
import java.lang.reflect.*;
import java.util.Arrays;

/** Re-serialize known board types through the original APK's generated parsers. */
public final class PageVariantProbe {
    static Object parse(Class<?> cls, InputStream in) throws Exception {
        try {
            Method direct=cls.getMethod("parseFrom",InputStream.class);
            return direct.invoke(null,in);
        } catch (NoSuchMethodException renamed) {
            // Continue with the adapter retained by these R8 builds.
        }
        // R8 renamed the static InputStream adapter in four of these five APKs.
        for (Method m : cls.getDeclaredMethods()) {
            if (Modifier.isStatic(m.getModifiers()) && Modifier.isPublic(m.getModifiers()) &&
                m.getReturnType()==cls && Arrays.equals(m.getParameterTypes(),new Class<?>[]{InputStream.class}))
                return m.invoke(null,in);
        }
        // Some generated adapters are removed. Their MessageLite parser still implements the interface.
        for (Method m : cls.getDeclaredMethods()) {
            if (Modifier.isStatic(m.getModifiers()) && Modifier.isPublic(m.getModifiers()) &&
                m.getReturnType()==cls && m.getParameterTypes().length==0) {
                Object instance=m.invoke(null);
                Object parser=cls.getMethod("getParserForType").invoke(instance);
                return Class.forName("com.google.protobuf.Parser").getMethod("parseFrom",InputStream.class).invoke(parser,in);
            }
        }
        throw new NoSuchMethodException("Missing message parser");
    }
    public static void main(String[] args) throws Exception {
        File root=new File(args[0]);
        String[][] types={{"header","EzyHeader$Header"},{"pages","EzyPageRouter$PageRouter"},
            {"router","EzyRouterRecord$RouterRecord"},{"snapshot","EzyPageSnapshot$PageSnapshot"},
            {"touch","EzySource$TouchSource"},{"commands","EzyCommand$CommandSource"},
            {"text","EzySource$TextSource"},{"geometry","EzySource$GeometrySource"},{"file","EzySource$FileSource"}};
        for (String[] type:types) {
            try (FileInputStream input=new FileInputStream(new File(root,type[0]+".bin"))) {
                Class<?> cls=Class.forName("com.zykj.board."+type[1]);
                Object record=parse(cls,input);
                byte[] bytes=(byte[])cls.getMethod("toByteArray").invoke(record);
                try(OutputStream out=new FileOutputStream(new File(root,type[0]+".out"))) { out.write(bytes); }
                System.out.println(type[0]+" OK "+bytes.length);
            } catch(Throwable error) {
                while(error instanceof InvocationTargetException)error=error.getCause();
                System.out.println(type[0]+" ERROR "+error);
            }
        }
    }
}
