"""Create a v6 starting snapshot with explicit native paint and a translated group."""
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[2]
evidence = root / 'reports/evidence/board'
identity = 'scaleX:1 scaleY:1 perSp2:1'
def graph(ident, kind, x, y, details):
    return f'childGraph {{id:"{ident}" graphEnum:{kind} matrix {{{identity} transX:{x} transY:{y}}} {details}}}'

title = graph('title', 'TEXT_GRAPH', 40, 35, 'sourceFileName:"1_text.bin" content:"画板图元 / Blackboard" paint {color:-14540254 textSize:28} outRect {right:450 bottom:70}')
oval = graph('oval', 'GEOMETRY_GRAPH', 50, 150, 'sourceFileName:"2_geometry.bin" paint {width:4 color:-14132901} outRect {right:140 bottom:100}')
triangle = graph('triangle', 'GEOMETRY_GRAPH', 230, 150, 'sourceFileName:"2_geometry.bin" sourceId:1 paint {width:4 color:-9000000 style:1} outRect {right:135 bottom:95} pointList {x:0 y:95} pointList {x:70 y:0} pointList {x:135 y:95}')
group = graph('group', 'GROUP_GRAPH', 170, 100, triangle)
image = graph('image', 'IMAGE_GRAPH', 440, 150, 'sourceFileName:"3_file.bin" filePath:"tiles.png" outRect {right:105 bottom:105}')
snapshot = f'cameraMatrix {{{identity}}} graphSnapshot {{id:"root" backgroundColor:-1 matrix {{{identity}}} outRect {{right:800 bottom:600}} {title} {oval} {group} {image}}}'

with tempfile.TemporaryDirectory() as tmp, ZipFile(root/'中育apk/错题本.apk') as apk:
    for name in apk.namelist():
        if name.endswith('.proto') and (name.startswith(('utils/', 'enums/')) or '/' not in name):
            apk.extract(name, tmp)
    encoded = subprocess.run(['protoc', '-I'+tmp, '-I/usr/include', '--encode=PageSnapshot', 'GraphSnapshot.proto'],
                             input=snapshot.encode(), capture_output=True, check=True).stdout
with ZipFile(evidence/'schema-artwork.zip') as src, ZipFile(evidence/'artwork-edit-base.zip', 'w', ZIP_DEFLATED) as out:
    for name in src.namelist():
        out.writestr(name, encoded if name == 'lesson/p1/snapshot.bin' else src.read(name))
    out.writestr('lesson/p1/header.bin', b'')
