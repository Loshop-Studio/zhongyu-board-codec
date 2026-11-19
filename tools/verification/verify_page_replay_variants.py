"""Resolve five original V6 schedulers and compare their seeks with the reference frames."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile
from page_audio_fixture import ROOT, BOARD
from verify_artwork_variants import APPS, PACKAGE, unique


def symbols(app, common):
    root=ROOT/'android'/app
    def dex(string):
        paths=subprocess.check_output(['rg','-l','-F','--glob','*.smali','--',string,str(root)],text=True)
        return unique(map(Path,paths.splitlines()))
    def methods(file):
        return re.findall(r'^\.method ([^\n]*?) ([^\s]+\([^\s]*)\n(.*?)^\.end method',file.read_text(),re.M|re.S)
    def match(file,rule):
        return unique(sig for flags,sig,body in methods(file) if 'public' in flags and 'static' not in flags and rule(sig,body))
    thread=dex('即将快进'.encode('unicode_escape').decode())
    ctrl=unique(root.glob('smali*/'+common['control'].replace('.','/')+'.smali'))
    return {**common,'thread':re.search(r'^\.class .* L([^;]+);',thread.read_text(),re.M)[1].replace('/','.'),
            'seek':match(thread,lambda sig,b:sig.endswith('(J)V') and 'Thread;->sleep(J)V' in b),
            'maximum':match(thread,lambda sig,b:sig.endswith('(J)V') and 'iput-wide p1' in b and 'invoke-' not in b),
            'version':match(thread,lambda sig,b:sig.endswith('(I)V') and 'iput p1' in b),
            'path':match(thread,lambda sig,b:sig.endswith('(Ljava/lang/String;)V') and '"path"' in b),
            'shutdown':match(thread,lambda sig,b:'ExecutorService;->shutdown()V' in b),
            'redraw':match(ctrl,lambda sig,b:'GraphControl:reDrawFixView' in b and sig.endswith('()V')),
            'matrixEnd':match(ctrl,lambda sig,b:'GraphControl:translationEnd' in b)}


def check(serial,target,reference,notebook):
    adb=['adb','-s',serial]
    def put(name,data):
        subprocess.run([*adb,'shell','-T','run-as',PACKAGE,'tee','files/'+name],input=data,
                       stdout=subprocess.DEVNULL,check=True,timeout=80)
    def read(name):
        return subprocess.check_output([*adb,'exec-out','run-as',PACKAGE,'cat','files/art-variant-result/'+name],timeout=30)
    existing={r['app']:r for r in json.loads((ROOT/'reports/evidence/art/artwork-edit-variants.json').read_text())['apps']}
    ref=json.loads(reference.read_text())
    input_digest=hashlib.sha256(notebook.read_bytes()).hexdigest()
    assert ref['input_sha256']==input_digest
    expected=ref['seek']
    results=[]
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for n in apk.namelist():
            if n.endswith('.proto') and ('/' not in n or n.startswith(('enums/','utils/'))):apk.extract(n,tmp)
        for app in APPS:
            data=(ROOT/'中育apk'/(app+'.apk')).read_bytes()
            digest=hashlib.sha256(data).hexdigest()
            assert digest==existing[app]['apk_sha256']
            p=symbols(app,existing[app]['symbols'])
            put('art-variant.apk',data)
            put('art-variant.properties',''.join(k+'='+v+'\n' for k,v in p.items()).encode())
            log=subprocess.check_output([*adb,'shell','am','instrument','-w','-e','pageReplay','true',
                         '-e','artworkVariant','true',PACKAGE+'/.ProbeRun'],timeout=65,text=True)
            assert 'INSTRUMENTATION_CODE: -1' in log and '23 native graph snapshots' in log,(app,log)
            samples=json.loads(read('paths.json'))
            states=[]
            for i,(sample,want) in enumerate(zip(samples,expected,strict=True)):
                raw=read(f'seek-{i}.bin')
                proto=subprocess.run(['protoc','-I'+tmp,'-I/usr/include','--decode=PageSnapshot.GraphSnapshot','GraphSnapshot.proto'],
                                     input=raw,capture_output=True,check=True).stdout.decode()
                nodes=re.findall(r'^childGraph \{\n(.*?)^\}',proto,re.M|re.S)
                ids=[re.search(r'^  id: "(.*?)"',n,re.M)[1] for n in nodes]
                text=next((m[1] for n in nodes if (m:=re.search(r'^  content: "(.*?)"',n,re.M))),'')
                dx=next((float(m[1]) for n in nodes if 'id: "ink"' in n and (m:=re.search(r'^    transX: (.+)$',n,re.M))),0)+sample['transient_dx']
                found={'ms':sample['ms'],'graph_ids':ids,'text':text,'ink_dx':dx,'active_path_end':sample['active_path_end']}
                assert found==want,(app,found,want)
                states.append(found)
            results.append(dict(app=app,apk_sha256=digest,scheduler=p['thread'],seek=p['seek'],states=states))
            print(app, len(states),flush=True)
    target.write_text(json.dumps(dict(input_sha256=input_digest,apps=results),
                                 ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('serial')
    args.add_argument('--edited',action='store_true',help='Verify the browser-rewritten notebook installed in the test harness')
    args.add_argument('--native-dir',type=Path,help='Keep the reference PNGs and raw callback traces')
    o=args.parse_args()
    if not o.serial.startswith('emulator-'):args.error('Supply an emulator serial')
    stem='page-replay-edited' if o.edited else 'page-replay'
    notebook=BOARD/('web-page-replay.zip' if o.edited else 'page-replay.zip')
    reference=BOARD/(stem+'-native.json')
    with tempfile.TemporaryDirectory() as temporary:
        frames=o.native_dir.resolve() if o.native_dir else Path(temporary)
        env=dict(os.environ,PAGE_REPLAY='1',NEW_NOTE_ZIP=str(notebook),BOARD_EVIDENCE_DIR=str(frames))
        subprocess.run(['bash',str(ROOT/'tools/verification/verify_page.sh'),o.serial],env=env,check=True,timeout=180)
        rows=json.loads((frames/'frames.json').read_text())
        forward=json.loads((frames/'forward.json').read_text())
        assert len(rows)==23 and rows[4]['active_path_end']==[150,100] and rows[10]['graph_ids']==[]
        assert rows[12]['text']=='Before' and rows[14]['text']=='After' and rows[17]['ink_dx']==40
        assert [r['text'] for r in forward]==['','After','After','After']
        final_ids=rows[19]['graph_ids']
        assert final_ids[:2]==['ink','title'] and len(final_ids)==(3 if o.edited else 2)
        if o.edited:assert final_ids[2].startswith('web-')
        reference.write_text(json.dumps(dict(apk='错题本',
             apk_sha256=hashlib.sha256((ROOT/'中育apk/错题本.apk').read_bytes()).hexdigest(),
             input_sha256=hashlib.sha256(notebook.read_bytes()).hexdigest(),
             android=subprocess.check_output(['adb','-s',o.serial,'shell','getprop','ro.build.version.release'],text=True).strip(),
             seek=rows,forward=forward),ensure_ascii=False,indent=2)+'\n')
        check(o.serial,ROOT/'reports/evidence/art'/(stem+'-variants.json'),reference,notebook)
