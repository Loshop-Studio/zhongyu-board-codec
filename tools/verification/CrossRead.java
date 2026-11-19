import java.io.FileInputStream;
import java.lang.reflect.InvocationTargetException;
import java.util.List;

/** Isolated check using the parser classes actually bundled in one APK, on Android ART. */
public final class CrossRead {
    public static void main(String[] args) {
        try (FileInputStream stream = new FileInputStream(args[1])) {
            boolean simple = args[0].equals("simple");
            Class<?> root = Class.forName(simple ? "com.zykj.view.EzySimpleBoardData$SimpleBoardData" : "com.zykj.sketch.EzyDrawBoard$DrawBoard");
            Object message = root.getMethod("parseFrom", java.io.InputStream.class).invoke(null, stream);
            if (simple) {
                List<?> strokes = (List<?>) root.getMethod("getPathList").invoke(message);
                System.out.println("SimpleBoard paths=" + strokes.size());
            } else {
                Object body = root.getMethod("getBoardBody").invoke(message);
                List<?> actions = (List<?>) body.getClass().getMethod("getActionContentList").invoke(body);
                int touch = 0;
                for (Object action : actions) {
                    if ("ACTION_TOUCH".equals(action.getClass().getMethod("getType").invoke(action).toString())) touch++;
                }
                System.out.println("Sketch actions=" + actions.size() + " touch records=" + touch);
            }
        } catch (Throwable error) {
            while (error instanceof InvocationTargetException) error = error.getCause();
            System.err.println(error.getClass().getName() + ": " + error.getMessage());
            System.exit(1);
        }
    }
}
