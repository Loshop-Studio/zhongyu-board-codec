"""Replay every recorded cursor sample with each original V6 scheduler and graphics path."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import uuid

from check_native_page_recording import from_zip, schema_reader
from verify_artwork_variants import APPS, PACKAGE, ROOT
from verify_page_replay_variants import symbols


def gestures(notebook):
    files = from_zip(notebook)
    parse = schema_reader(ROOT/'中育apk/错题本.apk')
    page, = parse('PageRouter', files['page_router.bin']).pageInfo
    prefix = page.name+'/'
    def read(kind, name):
        return parse(kind, files[prefix+name])
    header = read('Header', 'header.bin')
    route = read('RouterRecord','router.bin')
    clock, camera, cursors = 0, (1,1,0,0), []
    for record in route.commandRecord:
        for action in read('CommandSource',record.fileName).commandInfo:
            start = clock + (action.delayTime if action.isPlay else 0)
            end = start + (action.duration if action.isPlay else 0)
            clock = end
            if action.commandEnum == 7:
                m = parse('CommandSource.CommandInfo.Camera',action.data).lastMatrix
                assert m.skewX == m.skewY == 0
                camera = m.scaleX,m.scaleY,m.transX,m.transY
            if action.commandEnum != 11:
                continue
            c = parse('CommandSource.CommandInfo.CursorMove',action.data)
            info = read('TouchSource',c.sourceFileName).touchInfo[c.sourceId]
            times = [t.eventTime for t in info.touchEvent]
            assert action.isPlay and times == sorted(times) and times[-1]-times[0] == end-start
            sx,sy,tx,ty=camera
            points = [{'ms':start+t.eventTime-times[0], 'x':sx*t.x+tx,'y':sy*t.y+ty} for t in info.touchEvent]
            cursors.append(dict(start=start,end=end,points=points,color=info.paint.color,width=info.paint.width))
    return {name[len(prefix):]:data for name,data in files.items() if name.startswith(prefix)},header.duration,cursors


def expected(cursors,t):
    for shape in cursors:
        if shape['start'] <= t < shape['end']:
            last = next(p for p in reversed(shape['points']) if p['ms'] <= t)
            return dict(x=last['x'],y=last['y'],color=shape['color'],width=shape['width'],height=shape['width'])
    return None


def check(serial, notebook):
    if not serial.startswith('emulator-'): raise ValueError('Select a disposable emulator')
    members,duration,cursors=gestures(notebook)
    times=sorted({0,duration,*[ms for c in cursors for ms in (
        c['start']-1,c['end'],*[p['ms']+1 for p in c['points'][:-1] if p['ms']+1<c['end']]) if ms>=0]})
    times.append(cursors[0]['points'][1]['ms']+1)  # seek backwards after the terminal frame
    reports=run_variant_seeks(serial,members,duration,times,'cursor')
    for result in reports:
        app=result['app']
        rows=result['states']
        for ms,row in zip(times,rows,strict=True):
            want=expected(cursors,ms); got=row['cursor']
            assert ms==row['ms']
            if want is None: assert got is None, (app,ms,got)
            else:
                assert got is not None and got['color']==want['color'], (app,ms,got,want)
                assert all(math.isclose(got[k],want[k],abs_tol=.0001) for k in ('width','height','x','y')),(app,ms,got,want)
    return dict(input_sha256=hashlib.sha256(notebook.read_bytes()).hexdigest(),duration_ms=duration,
                gestures=cursors,checkpoint_count=len(times),apps=reports)


def run_variant_seeks(serial,members,duration,times,kind,configure=None):
    if not serial.startswith('emulator-'): raise ValueError('Select a disposable emulator')
    adb=['adb','-s',serial]
    def put(path,data):
        subprocess.run([*adb,'shell','-T','run-as',PACKAGE,'tee','files/'+path],input=data,stdout=subprocess.DEVNULL,check=True)
    folder=kind+'-'+uuid.uuid4().hex
    subprocess.run([*adb,'shell','run-as',PACKAGE,'mkdir','files/'+folder],check=True)
    try:
        for name,data in members.items():
            if '/' not in name: put(folder+'/'+name,data)
        refs={app['app']:app for app in json.loads((ROOT/'reports/evidence/art/artwork-edit-variants.json').read_bytes())['apps']}
        reports=[]
        for app in APPS:
            apk=(ROOT/'中育apk'/(app+'.apk')).read_bytes()
            digest=hashlib.sha256(apk).hexdigest()
            assert digest==refs[app]['apk_sha256']
            conf={**symbols(app,refs[app]['symbols']),'duration':str(duration),kind+'Times':','.join(map(str,times))}
            if configure: conf.update(configure(app,conf))
            put('art-variant.apk',apk)
            put('art-variant.properties',''.join(k+'='+v+'\n' for k,v in conf.items()).encode())
            log=subprocess.check_output([*adb,'shell','am','instrument','-w','-e','artworkVariant','true',
                                         '-e','cursorDirectory',folder,PACKAGE+'/.ProbeRun'],text=True,timeout=75)
            assert 'INSTRUMENTATION_CODE: -1' in log and 'native '+kind+' checkpoints' in log, (app,log)
            rows=json.loads(subprocess.check_output([*adb,'exec-out','run-as',PACKAGE,'cat','files/art-variant-result/paths.json']))
            reports.append(dict(app=app,apk_sha256=digest,scheduler=conf['thread'],seek_method=conf['seek'],states=rows))
    finally:
        subprocess.run([*adb,'shell','run-as',PACKAGE,'rm','-r','files/'+folder],check=True)
    return reports


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('serial');cli.add_argument('notebook',type=Path);cli.add_argument('output',type=Path)
    a=cli.parse_args()
    a.output.write_text(json.dumps(check(a.serial,a.notebook),ensure_ascii=False,indent=2)+'\n')
