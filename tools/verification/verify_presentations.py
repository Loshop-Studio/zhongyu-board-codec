"""Run the original Sketch slide control and callbacks against a local three-page deck."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
from verify_sketch_players import ROOT, BOARD, PACKAGE, APPS

def main(serial):
    if not serial.startswith('emulator-'):
        raise ValueError('Expected emulator serial')
    def adb(*args, **kw):
        return subprocess.run(['adb','-s',serial,*args],capture_output=True,check=True,timeout=70,**kw).stdout
    rows=[]
    graphs=[]
    for name in APPS:
        path=ROOT/'中育apk'/(name+'.apk')
        with ZipFile(path) as apk:
            assets=[n for n in apk.namelist() if n.startswith('assets/ppt/')]
        with path.open('rb') as src:
            adb('shell','-T',f"run-as {PACKAGE} sh -c 'cat > files/ppt-vendor.apk'",stdin=src)
        log=adb('shell','am','instrument','-w','-e','pptViewer','true',PACKAGE+'/.ProbeRun').decode()
        if 'INSTRUMENTATION_CODE: -1' not in log:
            raise RuntimeError(name+' '+log)
        data=json.loads(next(l.partition('presentation=')[2] for l in log.splitlines() if 'presentation=' in l))
        pid=data.pop('pid')
        system_log=adb('logcat','-d','--pid='+str(pid),'-s','AndroidProtocolHandler:E').decode()
        fallback=next(line.split('Unable to open asset URL: ',1)[1].strip() for line in system_log.splitlines() if 'Unable to open asset URL: file:///android_asset/ppt/demo.html' in line)
        data['failedAssetUrl']=fallback
        last=data['states'][-1]
        assert last['trace']==['load','Next','NxtSlide','Prev','GotoSlide:string','PrvSlide'],last
        assert all(s['imageWidth']==64 for s in data['states'])
        rows.append(dict(app=name,apk_sha256=sha256(path.read_bytes()).hexdigest(),packagedPptAssets=assets,**data))
        log=adb('shell','am','instrument','-w','-e','pptGraph','true',PACKAGE+'/.ProbeRun').decode()
        if 'INSTRUMENTATION_CODE: -1' in log:
            frames=json.loads(next(l.partition('graphs=')[2] for l in log.splitlines() if l.startswith('INSTRUMENTATION_RESULT: graphs=')))
            assert frames['slides'][-1]['layers'][-1]=='stroke'
            if 'native-presentation' in frames:
                deck,stroke=frames['native-presentation'][-1]['layers']
                assert deck['width']==640 and deck['height']==480 and stroke=='stroke'
            assert [r['ms'] for r in frames['slides-recording']]==[0,400,1200]
            if graphs: assert frames==graphs[0]['graphs'],name
            graphs.append(dict(app=name,graphs=frames))
        else:
            if name!='中育云笔记' or 'makeExtensionsImmutable' not in log:raise RuntimeError(name+' '+log)
            graphs.append(dict(app=name,loadError=next(l.strip() for l in log.splitlines() if 'NoSuchMethodError' in l)))
        print(name,last['trace'], 'graphs' if 'graphs' in graphs[-1] else graphs[-1]['loadError'],flush=True)
    out=ROOT/'reports/evidence/art/presentation-viewers.json'
    out.write_text(json.dumps(dict(fixture='sketch-presentations.zip',sha256=sha256((BOARD/'sketch-presentations.zip').read_bytes()).hexdigest(),apps=rows),ensure_ascii=False,indent=2)+'\n')
    graph_file=out.with_name('presentation-graphs.json')
    inputs=['web-sketch-presentation.zip']
    if 'native-presentation' in graphs[0]['graphs']:inputs.append('web-sketch-native-presentation.zip')
    graph_file.write_text(json.dumps(dict(inputs={n:sha256((BOARD/n).read_bytes()).hexdigest() for n in inputs},apps=graphs),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main(sys.argv[1])
