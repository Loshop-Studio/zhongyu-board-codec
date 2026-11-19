"""Create offline V5 fixtures for root transforms and two-pointer writing modes."""
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[2]
out = root / 'reports/evidence/board'
with tempfile.TemporaryDirectory() as tmp, ZipFile(root / '中育apk/错题本.apk') as apk:
    for name in ('DrawBoard.proto','SketchGraphSnapshot.proto'):
        (Path(tmp)/name).write_bytes(apk.read(name).removeprefix(b'\xef\xbb\xbf'))

    def encode(name, body):
        return subprocess.run(['protoc','-I'+tmp,'-I/usr/include','--encode='+name,'DrawBoard.proto'],
                              input=body.encode(),capture_output=True,check=True).stdout

    events = []
    def add(name, kind, body, snapshot=""):
        raw = encode(name, body)
        quoted = ''.join('\\%03o'%v for v in raw)
        events.append((kind, f'ActionContent{{type:{kind} action{{type_url:"type.googleapis.com/{name}" value:"{quoted}"}} {snapshot}}}'))

    def gesture(items):
        data = []
        for ms, action, xy in items:
            props = ' '.join(f'pointerProperties{{id:{i} toolType:2}} pointerCoords{{x:{x} y:{y}}}'
                             for i,(x,y) in enumerate(xy))
            x,y=xy[0]
            data.append(f'touchEvent{{eventTime:{10000+ms} action:{action} pointerCount:{len(xy)} x:{x} y:{y} {props}}}')
        add('ActionTouchEvent','ACTION_TOUCH',f'startTime:{10000+items[0][0]} endTime:{10000+items[-1][0]} '+ ' '.join(data))

    identity = 'graphSnapshot{matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]}'
    add('AudioStartAction','ACTION_AUDIO_START','startTime:10000 fileName:"first.wav"',identity)
    add('ActionModeConfig','ACTION_MODE','startTime:10001 mode:ACTION_WRITING')
    add('ActionGraphConfig','ACTION_GRAPH','startTime:10002 config{width:6 color:-16777216}')
    gesture([(30,0,[(40,50)]),(60,2,[(80,75)]),(90,1,[(100,95)])])
    add('ActionTranslation','ACTION_TRANS','startTime:10130 keep:true transX{value:20} transY{value:30}')
    add('ActionZoom','ACTION_ZOOM','startTime:10180 keep:true scaleX:2 scaleY:3 centerX:10 centerY:20')
    add('ActionTranslation','ACTION_TRANS','startTime:10230 transX{value:14}')
    add('ActionZoom','ACTION_ZOOM','startTime:10280 scaleX:1.5 scaleY:1 centerX:4 centerY:0')
    add('ActionModeConfig','ACTION_MODE','startTime:10300 mode:ACTION_WRITING_MOVE')
    gesture([(310,0,[(120,120)]),(325,2,[(125,125)]),(340,5,[(130,120),(170,160)]),
             (365,2,[(150,150),(210,190)]),(385,2,[(155,160),(215,200)]),
             (400,6,[(155,160),(215,200)]),(415,1,[(155,160)])])
    add('ActionModeConfig','ACTION_MODE','startTime:10430 mode:ACTION_WRITING_MOVE_VERTICAL')
    gesture([(440,0,[(310,120)]),(455,5,[(300,110),(360,190)]),(475,2,[(360,120),(430,210)]),
             (495,6,[(360,120),(430,210)]),(510,1,[(360,120)])])
    add('ActionTranslation','ACTION_TRANS','startTime:10530 transY{value:7}')
    add('ActionResetMatrix','ACTION_RESET_MATRIX','startTime:10550')
    add('ActionModeConfig','ACTION_MODE','startTime:10580 mode:ACTION_WRITING')
    gesture([(600,0,[(290,195)]),(630,2,[(380,260)]),(660,1,[(418,291)])])
    add('AudioStopAction','ACTION_AUDIO_STOP','startTime:11200 fileName:"first.wav"')
    def document(rows):
        return encode('DrawBoard','boardHead{version:5 width:640 height:480 type:2} boardBody{'+
                      ' '.join(row for _,row in rows)+'}')
    (out/'sketch-transform.bin').write_bytes(document([(k,r) for k,r in events if 'AUDIO' not in k]))
    with ZipFile(out/'sketch-recording.zip') as original, ZipFile(out/'sketch-transform.zip','w',ZIP_DEFLATED) as archive:
        archive.writestr('transform/actions.bin',document(events))
        archive.writestr('transform/res/audio/first.wav',original.read('recording/res/audio/first.wav'))
