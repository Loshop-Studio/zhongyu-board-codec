"""Build a two-page V6 notebook with two PCM clips, leading, middle and trailing silence."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipInfo, ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / 'reports/evidence/board'


def write_fixture(destination, split=False):
    with tempfile.TemporaryDirectory() as temp, ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for path in apk.namelist():
            if path.endswith('.proto') and ('/' not in path or path.startswith(('utils/', 'enums/'))):
                (Path(temp)/path).parent.mkdir(parents=True, exist_ok=True)
                (Path(temp)/path).write_bytes(apk.read(path).removeprefix(b'\xef\xbb\xbf'))

        def encode(schema, message, content):
            return subprocess.run(['protoc', '-I'+temp, '-I/usr/include',
                                   '--encode='+message, schema+'.proto'],
                                  input=content.encode(), check=True, capture_output=True).stdout

        with ZipFile(BOARD/'web-new-notebook.zip') as source:
            members = {p: source.read(p) for p in source.namelist()}
        with ZipFile(BOARD/'sketch-recording.zip') as sounds:
            for name in ('first.wav', 'second.wav'):
                members['lesson/res/audio/'+name] = sounds.read('recording/res/audio/'+name)
        records = []
        for name, delay, duration, flag in [('first.wav', 200, 1200, 'true'), ('second.wav', 400, 800, 'false')]:
            body = encode('Command', 'CommandSource.CommandInfo.AudioStart',
                          f'fileName:"{name}" duration:{duration}')
            wire = ''.join('\\%03o' % value for value in body)
            records.append(f'commandInfo {{delayTime:{delay} duration:{duration} isPlay:{flag} '
                           f'commandEnum:ACTION_AUDIO_START data:"{wire}"}}')
        for index, group in enumerate(([r] for r in records) if split else [records]):
            chunk = encode('Command', 'CommandSource', ' '.join(group))
            name = f'{index+1:04}_audio.bin'
            members['lesson/p1/'+name] = chunk
            signature = hashlib.sha256(chunk).hexdigest().lstrip('0').zfill(32)
            members['lesson/p1/router.bin'] += encode('RouterRecord', 'RouterRecord',
                f'audioRecord {{fileName:"{name}" validate:"{signature}"}}')
        members['lesson/p1/header.bin'] += encode('Header', 'Header', 'duration:2800')
        with ZipFile(destination, 'w', ZIP_DEFLATED) as out:
            for name, data in members.items():
                out.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('output', type=Path)
    args.add_argument('--split', action='store_true')
    options = args.parse_args()
    write_fixture(options.output, options.split)
