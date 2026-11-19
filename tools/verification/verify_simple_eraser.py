"""Replay controlled SimpleBoard contacts in the original two Views and read back their actual BINs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from build_instrumentation import build_probe

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'local.zy.simpleeraser'
STROKES = [
    (0xffbc3451, [(20,48),(260,48)]),
    (0xff147ca1, [(64,120),(64,208)]),
    (0xff7555a9, [(140,100),(260,200)]),
    (0xffb27132, [(100,140),(114,150)]),
    (0xff238258, [(282,190)]),
    (0xff415364, [(40,175),(40,175)]),
    (0xff863b88, [(175,210),(255,210)]),
]


def tap(name,x,y,**kwargs):
    return dict(name=name, contacts=[[0,x,y],[1,x,y]], **kwargs)


CASES = [
    dict(name='original',contacts=[],picture=True),
    tap('sparse-middle',160,48), tap('radius-interior',160,85),
    tap('bounds-top',160,8), tap('bounds-bottom',160,88),
    tap('rounded-radius-miss',130,8), tap('rounded-small-radius-miss',160,40,radius=8),
    tap('right-endpoint',260,48), tap('outside-wide-bounds',135,98),
    tap('short-stroke',90,144), tap('one-point',282,190),
    tap('overlapping',40,175), tap('exactly-two-radii',171,210),
    tap('small-radius',160,65,radius=8), tap('zoomed-hit',160,68,zoom=1.5),
    tap('zoomed-miss',160,81,zoom=1.5),
    dict(name='drag',contacts=[[0,160,48],[2,160,60],[1,40,175]],picture=True),
]


def run(*args, data=None):
    return subprocess.run(args, input=data, stdout=subprocess.PIPE, check=True).stdout


def seven_paths():
    rows = []
    for index, (color, points) in enumerate(STROKES):
        samples = ' '.join(f'point {{value:{x} value:{y}}}' for x, y in points)
        dashed = 'true' if index == 0 else 'false'
        rows.append(f'path {{ {samples} paint {{ color:{color-2**32} width:5 isDashed:{dashed} }} }}')
    return '\n'.join(rows).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial')
    parser.add_argument('out', type=Path)
    parser.add_argument('--read', type=Path, help='Reopen a previously exported BIN in both original Views')
    args = parser.parse_args()
    if not re.fullmatch(r'emulator-\d+', args.serial):
        parser.error('Use a disposable Android emulator')
    args.out.mkdir(parents=True, exist_ok=True)
    cases = [dict(name='reopened', contacts=[], picture=True)] if args.read else CASES
    sdk = Path(os.environ['ANDROID_HOME'])

    def adb(*cmd, data=None):
        return run(sdk/'platform-tools/adb', '-s', args.serial, *cmd, data=data)

    def put(name, content):
        adb('shell', '-T', f"run-as {PACKAGE} sh -c 'cat > {name}'", data=content)

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        schema = directory/'SimpleBoardData.proto'
        with ZipFile(ROOT/'中育apk/错题本.apk') as apk:
            schema.write_bytes(apk.read(schema.name).removeprefix(b'\xef\xbb\xbf'))

        def protobuf(mode, payload):
            return run('protoc', '-I'+tmp, '-I/usr/include', '--'+mode+'=SimpleBoardData', schema, data=payload)

        data = args.read.read_bytes() if args.read else protobuf('encode', seven_paths())
        (args.out/'input.bin').write_bytes(data)
        adb('install', '-r', build_probe(directory, sdk, PACKAGE, Path(__file__).with_name('SimpleEraserProbe.java')))
        reports = []
        for name, tag in [('错题本', 'mistake'), ('新测评', 'assessment')]:
            source = ROOT/'中育apk'/(name+'.apk')
            adb('shell', 'pm', 'clear', PACKAGE)
            adb('shell', 'run-as', PACKAGE, 'mkdir', '-p', 'files/input')
            put('files/target.apk', source.read_bytes())
            put('files/input/remote_draft.bin', data)
            put('files/cases.json', json.dumps(cases).encode())
            log = adb('shell', 'am', 'instrument', '-w', '-r', '-e', 'app', tag,
                      PACKAGE+'/.SimpleEraserProbe').decode()
            if 'INSTRUMENTATION_CODE: -1' not in log:
                raise RuntimeError(name+'\n'+log)
            target = args.out/name
            target.mkdir(exist_ok=True)
            results = []
            for case in cases:
                label = case['name']
                base = 'files/results/'+label+'/'
                payload = adb('exec-out', 'run-as', PACKAGE, 'cat', base+'result.bin')
                (target/(label+'.bin')).write_bytes(payload)
                if case.get('picture'):
                    image = adb('exec-out', 'run-as', PACKAGE, 'cat', base+'page.png')
                    (target/(label+'.png')).write_bytes(image)
                colors = [int(v) & 0xffffffff for v in re.findall(rb'color: (-?\d+)', protobuf('decode', payload))]
                results.append({**case, 'surviving_colors': colors, 'bin_sha256': hashlib.sha256(payload).hexdigest()})
            reports.append({'app': name, 'apk_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'cases': results})
            print(name, len(results), flush=True)
        assert reports[0]['cases'] == reports[1]['cases']
        (args.out/'native.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
