import android.app.Application;

import java.io.*;
import java.lang.reflect.*;
import java.util.*;

/** Resolve the methods identified in each original DEX and export native snapshots after each command. */
public final class ArtworkVariantProbe {
    static String descriptor(Class<?> type) {
        if(type.isArray())return type.getName().replace('.','/');
        if(type.isPrimitive())return type==Void.TYPE?"V":type==Boolean.TYPE?"Z":type==Long.TYPE?"J":type==Integer.TYPE?"I":type==Float.TYPE?"F":type==Double.TYPE?"D":type==Byte.TYPE?"B":type==Short.TYPE?"S":"C";
        return "L"+type.getName().replace('.','/')+";";
    }
    static Method method(Class<?> c,String name,int count) throws Exception {
        for(Method m:c.getMethods()) {
            if(m.getParameterTypes().length!=count || !name.startsWith(m.getName()+"("))continue;
            StringBuilder sig=new StringBuilder(m.getName()).append('(');
            for(Class<?> type:m.getParameterTypes())sig.append(descriptor(type));
            if(sig.append(')').append(descriptor(m.getReturnType())).toString().equals(name))return m;
        }
        throw new NoSuchMethodException(c.getName()+"."+name);
    }
    static Constructor<?> constructor(Class<?> c,int count) throws Exception {
        for(Constructor<?> k:c.getConstructors())if(k.getParameterTypes().length==count)return k;
        throw new NoSuchMethodException(c.getName()+" constructor "+count);
    }
    static Object instance(Class<?> c) throws Exception {
        for(Field field:c.getDeclaredFields())if(Modifier.isStatic(field.getModifiers()) && field.getType()==c) {
            field.setAccessible(true);return field.get(null);
        }
        throw new NoSuchFieldException(c.getName());
    }
    static Object read(Class<?> c,File file) throws Exception {
        try(InputStream in=new FileInputStream(file)) {return PageVariantProbe.parse(c,in);}
    }
    static void capture(Object control,Method snapshot,File output) throws Exception {
        Object graph=snapshot.invoke(control);
        try(FileOutputStream out=new FileOutputStream(output)) {
            out.write((byte[])graph.getClass().getMethod("toByteArray").invoke(graph));
        }
    }
    public static String run(Application app,File base,File edited,File config,File output) throws Exception {
        Properties p=new Properties();
        try(InputStream file=new FileInputStream(config)){p.load(file);}
        Class<?> utils=Class.forName(p.getProperty("appUtils"));
        method(utils,p.getProperty("appInit"),1).invoke(null,app);
        Class<?> controller=Class.forName(p.getProperty("control")),loaderType=Class.forName(p.getProperty("loader"));
        Object loader=constructor(loaderType,0).newInstance();
        method(loaderType,p.getProperty("loadPath"),1).invoke(loader,edited.getPath());
        Constructor<?> init=constructor(controller,3);
        Class<?>[] types=init.getParameterTypes();
        Object adapter=constructor(types[0],0).newInstance();
        Constructor<?> makeLayers=constructor(types[1],4);
        Class<?>[] ls=makeLayers.getParameterTypes();
        Object layers=makeLayers.newInstance(ArtworkCommandProbe.layer(ls[0]),ArtworkCommandProbe.layer(ls[1]),null,null);
        Object control=init.newInstance(adapter,layers,constructor(types[2],2).newInstance(800,600));
        method(controller,p.getProperty("draw"),1).invoke(control,false);
        if (p.containsKey("thread")) return PageReplayVariant.run(p,loader,adapter,control,edited,output);
        Class<?> pageType=Class.forName("com.zykj.board.EzyPageSnapshot$PageSnapshot");
        Object page=read(pageType,new File(base,"snapshot.bin"));
        Object initial=method(pageType,p.getProperty("pageGraph"),0).invoke(page);
        Class<?> graphUtils=Class.forName(p.getProperty("graphUtils"));
        Object root=method(graphUtils,p.getProperty("buildGraph"),2).invoke(instance(graphUtils),loader,initial);
        method(controller,p.getProperty("controlInit"),1).invoke(control,root);
        Class<?> factory=Class.forName(p.getProperty("factory"));
        Object executor=constructor(factory,3).newInstance(loader,adapter,control);
        Method execute=method(factory,p.getProperty("execute"),3);
        Method snapshot=method(controller,p.getProperty("snapshot"),0);
        Class<?> commandType=Class.forName("com.zykj.board.EzyCommand$CommandSource");
        Method list=method(commandType,p.getProperty("commands"),0);
        output.mkdirs();
        int i=0;
        capture(control,snapshot,new File(output,"step-0.bin"));
        for(String name:p.getProperty("files").split(",")) {
            Object record=read(commandType,new File(edited,name));
            for(Object cmd:(List<?>)list.invoke(record)) {
                execute.invoke(executor,false,cmd,0L);
                capture(control,snapshot,new File(output,"step-"+(++i)+".bin"));
            }
        }
        Object finalPage=read(pageType,new File(edited,"snapshot.bin"));
        Object finalSnapshot=method(pageType,p.getProperty("pageGraph"),0).invoke(finalPage);
        Object restored=method(graphUtils,p.getProperty("buildGraph"),2).invoke(instance(graphUtils),loader,finalSnapshot);
        method(controller,p.getProperty("controlInit"),1).invoke(control,restored);
        capture(control,snapshot,new File(output,"restored.bin"));
        if(i!=Integer.parseInt(p.getProperty("count","6")))throw new IllegalStateException("command count "+i);
        return i+" commands replayed, "+(i+2)+" native graph snapshots captured";
    }
}
