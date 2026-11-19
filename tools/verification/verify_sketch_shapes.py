"""Check static Sketch shape files in the shipped recorder and player on a disposable emulator."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

from PIL import Image, ImageChops, ImageFilter
from build_instrumentation import build_probe, ROOT
from compare_sketch_render import paper_rectangle


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compare(native, editor):
    screen = Image.open(editor).convert('RGB')
    rect = paper_rectangle(screen)
    resized = screen.crop(rect).resize(native.size, Image.Resampling.LANCZOS)
    def mask(image):
        return image.convert('L').point(lambda n: 255 if n < 155 else 0)
    a, b = mask(native), mask(resized)
    def overlap(a, b): return ImageChops.darker(a,b).histogram()[255]
    shared = overlap(a,b)
    counts = [im.histogram()[255] for im in (a,b)]
    near = [overlap(a,b.filter(ImageFilter.MaxFilter(3))),overlap(b,a.filter(ImageFilter.MaxFilter(3)))]
    assert min(counts)>1000 and min(x/n for x,n in zip(near,counts))>0.98, (rect,counts,near)
    # Independently check the drawn outlines and the locations of the unused modes.
    features = {'control':(100,52), 'rectangle_top':(115,110), 'rectangle_right':(245,155),
                'rectangle_bottom':(155,210), 'rectangle_left':(65,155), 'ellipse_left':(340,315),
                'ellipse_right':(560,315), 'ellipse_top':(450,250), 'ellipse_bottom':(450,380)}
    clear = [(155,155),(450,315),(345,253),(85,335),(365,85)]
    for im in (a,b):
        for key,(x,y) in features.items():
            assert im.crop((x-3,y-3,x+4,y+4)).getbbox(), key
        for x,y in clear:
            assert not im.crop((x-3,y-3,x+4,y+4)).getbbox(), (x,y)
    return dict(browser_crop=rect,native_dark=counts[0],web_dark=counts[1],same_pixel=shared,
                native_within_one_pixel=near[0],web_within_one_pixel=near[1])


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('serial')
    cli.add_argument('browser',type=Path,help='Output from browser-roundtrip.cjs --sketch-shapes')
    cli.add_argument('out',type=Path)
    args=cli.parse_args()
    if not re.fullmatch(r'emulator-\d+',args.serial):
        cli.error('Use a disposable Android emulator')
    args.out.mkdir(parents=True,exist_ok=True)
    sdk=Path(os.environ.get('ANDROID_HOME','/home/jdz/dev/android-sdk'))
    package='local.zy.boardprobe'
    apps=('错题本','优课畅学','新测评','随身答','中育云笔记')
    cases={}
    for v in (2,3,4,5):
        prefix=f'v{v}-' if v<5 else ''
        raw=(ROOT/f'reports/evidence/board/sketch-shapes/raw-v{v}.bin').read_bytes()
        web=(args.browser/(prefix+'web.bin')).read_bytes()
        rect=(args.browser/(prefix+'rect.bin')).read_bytes()
        assert raw==(args.browser/(prefix+'untouched.bin')).read_bytes()
        assert web==(args.browser/(prefix+'redo.bin')).read_bytes()
        assert rect==(args.browser/(prefix+'undo.bin')).read_bytes()
        cases[f'raw-v{v}']=raw
        cases[f'rect-v{v}']=rect
        cases[f'web-v{v}']=web

    def adb(*args_,data=None):
        return subprocess.run([sdk/'platform-tools/adb','-s',args.serial,*args_],input=data,
                              capture_output=True,check=True).stdout

    def put(path,data):
        adb('shell','-T',f"run-as {package} sh -c 'cat > files/{path}'",data=data)

    def get(path):
        return adb('exec-out','run-as',package,'cat','files/'+path)

    sources=Path(__file__).parent
    rows=[]
    originals={}
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp)
        probe=build_probe(work,sdk,package,sources/'SketchShapesProbe.java',sources/'NativePlayerProbe.java')
        adb('install','-r',probe)
        for name,data in cases.items():
            adb('shell','run-as',package,'mkdir','-p','files/'+name)
            put(name+'/actions.bin',data)
        jpeg_input=(args.browser/'v1-web.zip').read_bytes()
        with ZipFile(io.BytesIO(jpeg_input)) as legacy:
            adb('shell','run-as',package,'mkdir','-p','files/jpeg-v1/res')
            for member in ('actions.bin','header.bin','thumbnail.jpg','res/diagram.jpg'):
                put('jpeg-v1/'+member,legacy.read('note/'+member))
        for app in apps:
            apk=(ROOT/'中育apk'/(app+'.apk')).read_bytes()
            put('reader.apk',apk)
            for name in cases:
                for mode in ('player','recorder'):
                    adb('shell','run-as',package,'rm','-f','files/'+name+'/'+mode+'.json','files/'+name+'/'+mode+'.png')
            adb('shell','run-as',package,'rm','-f','files/jpeg-v1/recorder.png','files/jpeg-v1/recorder.json')
            log=adb('shell','am','instrument','-w','-e','cases',','.join([*cases,'jpeg-v1']),package+'/.SketchShapesProbe').decode()
            row={'app':app,'apk_sha256':sha(apk)}
            if 'INSTRUMENTATION_CODE: -1' not in log:
                causes=re.findall(r'(?:Caused by: )?(java\.lang\.NoSuchMethodError:[^\n]+)',log)
                if app!=apps[-1] or not causes or 'makeExtensionsImmutable' not in causes[-1]:
                    raise RuntimeError(log)
                row.update(status='load_failed',cause=causes[-1])
            else:
                row.update(status='opened',cases={})
                assert 'jpeg-v1=recorder=0/images=1' in log and json.loads(get('jpeg-v1/recorder.json'))==[], log
                jpeg_png=get('jpeg-v1/recorder.png')
                jpeg_rgb=sha(Image.open(io.BytesIO(jpeg_png)).convert('RGB').tobytes())
                if app==apps[0]:
                    (args.out/'web-v1-native.png').write_bytes(jpeg_png)
                    originals['jpeg']=jpeg_rgb
                assert originals['jpeg']==jpeg_rgb
                row['jpeg_v1']={'recorder_images':1,'editable_strokes':0,'rgb_sha256':jpeg_rgb}
                for name in cases:
                    expected=1 if name.startswith('raw') else 2 if name.startswith('rect') else 3
                    modes={}
                    for mode in ('recorder','player'):
                        path=name+'/'+mode
                        points=json.loads(get(path+'.json'))
                        assert len(points)==expected and points[0]==[[40,45],[175,60]], (app,path,points)
                        if len(points)>1:
                            assert 0 < points[1][-1][0]-points[1][0][0] <= 0.51 and len(points[1])==10
                        if len(points)>2:
                            assert points[2][-1][1] > points[2][0][1] and len(points[2])>16
                        png=get(path+'.png')
                        image=Image.open(io.BytesIO(png)).convert('RGB')
                        if app==apps[0] and mode=='recorder' and (name=='raw-v5' or name.startswith('web-v')):
                            (args.out/(name+'-native.png')).write_bytes(png)
                            (args.out/(name+'-points.json')).write_text(json.dumps(points)+'\n')
                        fingerprint=sha(image.tobytes())
                        key=name
                        evidence=(points,fingerprint)
                        if key not in originals: originals[key]=evidence
                        assert originals[key]==evidence, (app,path,fingerprint)
                        modes[mode]={'path_lengths':list(map(len,points)),'rgb_sha256':fingerprint}
                    row['cases'][name]=modes
            print(app,row['status'],flush=True)
            rows.append(row)
    pixels={}
    for v in (2,3,4,5):
        prefix=f'v{v}-' if v<5 else ''
        pixels[f'v{v}']=compare(Image.open(args.out/f'web-v{v}-native.png'),args.browser/(prefix+'editor.png'))
        for name in ('web.bin','editor.png'):
            (args.out/(prefix+name)).write_bytes((args.browser/(prefix+name)).read_bytes())
    pixels['v1']=compare(Image.open(args.out/'web-v1-native.png'),args.browser/'v1-editor.png')
    for name in ('v1-web.zip','v1-editor.png'):
        (args.out/name).write_bytes((args.browser/name).read_bytes())
    report=dict(input_sha256={**{name:sha(data) for name,data in cases.items()},'jpeg-v1':sha(jpeg_input)},apps=rows,pixels=pixels,
                browser={'untouched_bytes_match':True,'undo_equals_rectangle':True,'redo_equals_export':True})
    (args.out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__': main()
