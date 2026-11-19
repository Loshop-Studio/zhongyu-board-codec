"""Construct Sketch image actions and an older image snapshot using the APK schemas."""
import io
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/evidence/board"
IDENTITY = "matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]"

def image(fmt, palette):
    im = Image.new("RGB", (64, 40), palette[0])
    draw = ImageDraw.Draw(im)
    draw.rectangle((32, 0, 63, 19), fill=palette[1])
    draw.rectangle((0, 20, 31, 39), fill=palette[2])
    out = io.BytesIO()
    im.save(out, fmt)
    return out.getvalue()

def main():
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT / "中育apk/错题本.apk") as apk:
        for name in ("DrawBoard.proto", "SketchGraphSnapshot.proto"):
            (Path(tmp)/name).write_bytes(apk.read(name).removeprefix(b"\xef\xbb\xbf"))

        def encode(kind, body):
            return subprocess.run(["protoc", "-I"+tmp, "-I/usr/include", "--encode="+kind, "DrawBoard.proto"],
                                  input=body.encode(), capture_output=True, check=True).stdout

        def anymsg(kind, body):
            return 'type_url:"type.googleapis.com/'+kind+'" value:"'+''.join('\\%03o'%v for v in encode(kind,body))+'"'

        def action(kind, field, body, graph=""):
            return f"ActionContent{{type:{field} action{{{anymsg(kind,body)}}} {graph}}}"

        def line(t, x, y, xx, yy):
            body = " ".join(f"touchEvent{{eventTime:{t+i*10} action:{a} pointerCount:1 x:{px} y:{py} pointerProperties{{toolType:2}} pointerCoords{{x:{px} y:{py}}}}}"
                            for i,(a,px,py) in enumerate([(0,x,y),(2,xx,yy),(1,xx,yy)]))
            return action("ActionTouchEvent","ACTION_TOUCH",f"startTime:{t} endTime:{t+20} "+body)

        def asset(t, name, flag, w, h):
            return action("ActionImageConfig","ACTION_IMAGE",f'startTime:{t} path:"{name}" width:{w} height:{h} viewWidth:640 viewHeight:480 positionFlag:{flag}')

        common = [
            action("ActionModeConfig","ACTION_MODE","startTime:10001 mode:ACTION_WRITING"),
            action("ActionGraphConfig","ACTION_GRAPH","startTime:10002 config{width:9 color:-16777216}"),
            line(10020,80,220,565,242),
            asset(10100,"center.png",0,192,120),
            action("ActionTranslation","ACTION_TRANS","startTime:10160 keep:true transX{value:24} transY{value:18}"),
            asset(10200,"icons/upper.jpg",2,96,60),
            action("ActionTranslation","ACTION_TRANS","startTime:10240 keep:true transY{value:28}"),
            line(10300,160,315,509,175),
        ]
        body = lambda rows: encode("DrawBoard","boardHead{version:5 width:640 height:480 type:1} boardBody{"+' '.join(rows)+'}')
        assets = {"res/center.png":image("PNG",("#10a080","#2040c0","#f09820")),
                  "res/icons/upper.jpg":image("JPEG",("#e82848","#f8d848","#3058b0"))}
        with ZipFile(OUT/"sketch-images.zip","w",ZIP_DEFLATED) as z:
            z.writestr("illustration/actions.bin",body(common))
            for name,b in assets.items():z.writestr("illustration/"+name,b)
        graph = ('graphSnapshot{'+IDENTITY+' childGraph{graphType:IMAGE_GRAPH color:-2147483648 matrix:[1,0,94,0,1,81,0,0,1] '
                 'childExtendMatrix:[1,0,0,0,1,0,0,0,1] outRect{right:128 bottom:80} extra{'+
                 anymsg("File",'fileName:"center.png" width:128 height:80 viewWidth:640 viewHeight:480')+'}}}')
        requested = 'path:"center.png" width:192 height:120 viewWidth:640 viewHeight:480 positionFlag:0'
        with ZipFile(OUT/"sketch-image-versions.zip","w",ZIP_DEFLATED) as z:
            for v in range(1,6):
                head = f"boardHead{{version:{v} width:640 height:480 type:1}}"
                if v == 1:
                    event = anymsg("ActionImageConfig",requested)
                    payload = encode("DrawBoardV1",head+" boardBodyV1{ActionContent{"+event+"}}")
                else:
                    event = action("ActionImageConfig","ACTION_IMAGE",requested,graph)
                    payload = encode("DrawBoard",head+" boardBody{"+event+"}")
                z.writestr(f"image-v{v}/actions.bin",payload)
                z.writestr(f"image-v{v}/res/center.png",assets["res/center.png"])
        recorded = [action("AudioStartAction","ACTION_AUDIO_START",'startTime:10000 fileName:"first.wav"',"graphSnapshot{"+IDENTITY+"}"),
                    *common,action("ActionPrevAction","ACTION_PREV","startTime:10600",graph),
                    action("AudioStopAction","ACTION_AUDIO_STOP",'startTime:11200 fileName:"first.wav"',graph)]
        with ZipFile(OUT/"sketch-image-recording.zip","w",ZIP_DEFLATED) as z, ZipFile(OUT/"sketch-recording.zip") as sound:
            z.writestr("image-recording/actions.bin",body(recorded))
            z.writestr("image-recording/res/audio/first.wav",sound.read("recording/res/audio/first.wav"))
            for name,b in assets.items():z.writestr("image-recording/"+name,b)

if __name__=="__main__":main()
