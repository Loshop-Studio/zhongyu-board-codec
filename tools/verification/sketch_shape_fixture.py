"""Build a V5 static note with a writing control and both unhandled shape modes."""
from pathlib import Path
from io import BytesIO
import subprocess
import tempfile
from zipfile import ZipFile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/evidence/board/sketch-shapes'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # A V1 recorder opens thumbnail.jpg as a bitmap. Give it a known control
    # line and the same 640 x 480 canvas as the other version fixtures.
    page = Image.new('RGB',(640,480),'white')
    ImageDraw.Draw(page).line([(40,45),(175,60)],fill=(47,109,202),width=6)
    image = BytesIO()
    page.save(image,'JPEG',quality=95)
    with ZipFile(OUT.parent/'sketch-thumbnails/backing-v1.zip') as source, ZipFile(OUT/'raw-v1.zip','w') as target:
        for item in source.infolist():
            target.writestr(item,image.getvalue() if item.filename=='note/thumbnail.jpg' else source.read(item))
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT / '中育apk/错题本.apk') as apk:
        for name in ('DrawBoard.proto', 'SketchGraphSnapshot.proto'):
            (Path(tmp) / name).write_bytes(apk.read(name).removeprefix(b'\xef\xbb\xbf'))

        def encode(name, content):
            return subprocess.run(['protoc', '-I'+tmp, '-I/usr/include', '--encode='+name,
                                   'DrawBoard.proto'], input=content.encode(), capture_output=True, check=True).stdout

        records = []

        def add(kind, name, fields):
            value = ''.join('\\%03o' % byte for byte in encode(name, fields))
            records.append(f'ActionContent{{type:{kind} action{{type_url:"type.googleapis.com/{name}" value:"{value}"}}}}')

        for i, (mode, color, a, b) in enumerate([
                ('WRITING', -13668918, (40, 45), (175, 60)),
                ('SHAPE_RECT', -65536, (85, 335), (190, 401)),
                ('SHAPE_CIRCLE', -16751616, (300, 85), (430, 165))]):
            start = 10000 + i * 100
            add('ACTION_MODE', 'ActionModeConfig', f'startTime:{start} mode:ACTION_{mode}')
            add('ACTION_GRAPH', 'ActionGraphConfig', f'startTime:{start+1} config{{width:6 color:{color}}}')
            events = []
            for j, (action, (x, y)) in enumerate([(0, a), (2, b), (1, b)]):
                events.append(f'touchEvent{{eventTime:{start+2+j} action:{action} pointerCount:1 x:{x} y:{y} '
                              f'pointerProperties{{toolType:2}} pointerCoords{{x:{x} y:{y}}}}}')
            add('ACTION_TOUCH', 'ActionTouchEvent', f'startTime:{start+2} endTime:{start+4} '+' '.join(events))
        touch = encode('Touch', 'pointF{x:40 y:45} pointF{x:175 y:60}')
        packed = ''.join('\\%03o' % byte for byte in touch)
        identity = 'matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]'
        graph = ('graphSnapshot{' + identity + ' name:"source-root" childGraph{graphType:WRITING_GROUP_GRAPH '
                 + identity + ' name:"source-group" childGraph{graphType:STROKE_GRAPH ' + identity +
                 ' name:"source-ink" color:-13668918 width:6 extra{type_url:"type.googleapis.com/Touch" value:"' + packed + '"}}}}')
        for version in (2,3,4,5):
            rows = list(records)
            for i, mode in enumerate(('WRITING','SHAPE_RECT','SHAPE_CIRCLE')):
                index = i*3+2
                if version == 2:
                    rows[index] = rows[index][:-1]+graph+'}'
                if version == 3:
                    reset = f'resetData{{modeConfig:ACTION_{mode} graphConfig{{color:-13668918 width:6}} action{{}}}}'
                    rows[index] = rows[index][:-1]+reset+'}'
            fields = f'boardHead{{version:{version} width:640 height:480 createDate:1700000000 type:1}} boardBody{{'
            (OUT / f'raw-v{version}.bin').write_bytes(encode('DrawBoard', fields + ' '.join(rows) + '}'))


if __name__ == '__main__':
    main()
