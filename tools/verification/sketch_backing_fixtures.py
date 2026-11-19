"""Build two controlled inputs for RecordControl's JPEG migration branch from a real recorder ZIP."""
from copy import copy
from io import BytesIO
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'reports/evidence/board/sketch-thumbnails'


def generate():
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT/'中育apk/错题本.apk') as apk, ZipFile(OUT/'native.zip') as src:
        for name in ('DrawBoard.proto', 'SketchGraphSnapshot.proto', 'SketchHeader.proto'):
            (Path(tmp)/name).write_bytes(apk.read(name).removeprefix(b'\xef\xbb\xbf'))

        def convert(mode, message, proto, data):
            return subprocess.run(['protoc', '-I'+tmp, '-I/usr/include', '--'+mode+'='+message, proto],
                                  input=data, capture_output=True, check=True).stdout

        for version in (1, 5):
            with ZipFile(OUT/f'backing-v{version}.zip', 'w') as out:
                for member in src.infolist():
                    data = src.read(member)
                    if member.filename == 'note/actions.bin':
                        board = convert('decode', 'DrawBoard', 'DrawBoard.proto', data)
                        if version == 1:
                            # Old header with a recent date and no history. The JPEG is smaller than the view.
                            board = board.split(b'boardBody {', 1)[0].replace(b'version: 5', b'version: 1')
                            data = convert('encode', 'DrawBoardV1', 'DrawBoard.proto', board)
                        else:
                            # Keep the original two history records, change only the creation date.
                            board = re.sub(rb'createDate: \d+', b'createDate: 1', board, count=1)
                            data = convert('encode', 'DrawBoard', 'DrawBoard.proto', board)
                    elif member.filename == 'note/header.bin':
                        header = convert('decode', 'Header', 'SketchHeader.proto', data)
                        if version == 1:
                            header = header.replace(b'version: 5', b'version: 1')
                        else:
                            header = re.sub(rb'createDate: \d+', b'createDate: 1', header, count=1)
                        data = convert('encode', 'Header', 'SketchHeader.proto', header)
                    elif version == 1 and member.filename == 'note/thumbnail.jpg':
                        preview = BytesIO()
                        Image.open(BytesIO(data)).resize((320, 240), Image.Resampling.LANCZOS).save(preview, 'JPEG', quality=70)
                        data = preview.getvalue()
                    out.writestr(copy(member), data)


if __name__ == '__main__':
    generate()
