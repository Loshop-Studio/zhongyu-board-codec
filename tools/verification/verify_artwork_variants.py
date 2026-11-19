"""Replay the browser's Blackboard v6 edits with each supplied APK's actual controller."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
BOARD=ROOT/'reports/evidence/board'
PACKAGE='local.zy.boardprobe'
APPS=('错题本','优课畅学','新测评','随身答','中育云笔记')
SNAP='Lcom/zykj/board/EzyPageSnapshot$PageSnapshot$GraphSnapshot;'
ARGS='(ZLcom/zykj/board/EzyCommand$CommandSource$CommandInfo;J)'


def image_state(snapshot):
    graph = re.search(r'^childGraph \{\n  id: "image"\n(.*?)^\}',snapshot.decode(),re.M|re.S)
    if not graph or 'graphEnum: IMAGE_GRAPH' not in graph[1]:
        raise ValueError('missing top-level image in native snapshot')
    matrix = re.search(r'^  matrix \{\n(.*?)^  \}',graph[1],re.M|re.S)
    fields = dict((k,float(v)) for k,v in re.findall(r'^    (\w+): (.*)$',matrix[1],re.M))
    sequence = ('scaleX','skewX','transX','skewY','scaleY','transY','perSp0','perSp1','perSp2')
    return [fields.get(k,0) for k in sequence]
def unique(seq):
    values=list(seq)
    if len(values)!=1: raise ValueError(f'Expected one result, found {values}')
    return values[0]
def mapping(app):
    root=ROOT/'android'/app
    def search(needle):
        cmd=['rg','-l','-F','--glob','*.smali','--',needle,str(root)]
        return list(map(Path,subprocess.check_output(cmd,text=True).splitlines()))
    def methods(file):
        return [(flags,sig,body) for flags,sig,body in re.findall(r'^\.method ([^\n]*?) ([^\s]+\([^\s]*)\n(.*?)^\.end method',file.read_text(),re.M|re.S)]
    def sig(file,find):
        return unique(s for f,s,b in methods(file) if find(f,s,b))
    def marker(file,text):
        return sig(file,lambda f,s,b:text in b)
    def cls(file):
        desc=re.search(r'^\.class .* L([^;\n]+);',file.read_text(),re.M)
        return desc[1].replace('/','.')
    def only(leaf):
        return unique(root.glob('smali*/com/zykj/board/'+leaf+'.smali'))
    control=unique(search('"GraphControl:init -> "'))
    graph=unique(search('"pageSnapshot.paint"'))
    factory=unique(f for f in search(ARGS) if any(ARGS in s for _,s,_ in methods(f)) and ' constructor <init>(' in f.read_text() and 'GraphRemove;' in f.read_text())
    # The cache source loader retains SoftReferences; the DB-backed loader shares the path marker.
    loader=unique(f for f in search('"pageRootPath"') if 'Ljava/lang/ref/SoftReference;' in f.read_text() and any('(Ljava/lang/String;)V' in s and '"pageRootPath"' in b for _,s,b in methods(f)))
    utils=unique(f for f in search('"app is null."') if '/blankj/utilcode/' in f.as_posix())
    page=only('EzyPageSnapshot$PageSnapshot')
    commands=only('EzyCommand$CommandSource')
    lists=[s for f,s,b in methods(commands) if 'public' in f and 'static' not in f and s.endswith('()Ljava/util/List;') and 'return-object' in b]
    list_getter='getCommandInfoList()Ljava/util/List;' if 'getCommandInfoList()Ljava/util/List;' in lists else unique(lists)
    return {
        'control':cls(control),'controlInit':marker(control,'"GraphControl:init -> "'),
        'draw':sig(control,lambda f,s,b:s.endswith('(Z)V') and 'iput-boolean p1, p0' in b),
        'snapshot':sig(control,lambda f,s,b:s.endswith('()'+SNAP)),
        'graphUtils':cls(graph),'buildGraph':marker(graph,'"pageSnapshot.paint"'),
        'factory':cls(factory),'execute':sig(factory,lambda f,s,b:ARGS in s),
        'loader':cls(loader),'loadPath':sig(loader,lambda f,s,b:s.endswith('(Ljava/lang/String;)V') and '"pageRootPath"' in b),
        'appUtils':cls(utils),'appInit':sig(utils,lambda f,s,b:s.endswith('(Landroid/app/Application;)V') and '"app is null."' in b),
        'pageGraph':sig(page,lambda f,s,b:'static' not in f and s.endswith('()'+SNAP)),
        'commands':list_getter,
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial',nargs='?')
    parser.add_argument('--symbols',action='store_true')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--create',action='store_true',help='Replay the five artwork insertions from web-artwork-created.zip')
    modes.add_argument('--image',action='store_true',help='Replay the image transform and drag from web-page-image.zip')
    args=parser.parse_args()
    stem,filename,count=(('image','web-page-image.zip',2) if args.image else
                         ('create','web-artwork-created.zip',10) if args.create else
                         ('edit','web-artwork-edited.zip',6))
    mappings={app:mapping(app) for app in APPS}
    if args.symbols:
        print(json.dumps(mappings,ensure_ascii=False,indent=2))
        return
    if not args.serial or not args.serial.startswith('emulator-'):parser.error('Supply an emulator serial')
    adb=os.environ.get('ADB','adb')
    def device(*arguments,data=None):
        return subprocess.check_output([adb,'-s',args.serial,*arguments],input=data)
    def put(name,data):
        subprocess.run(
            [adb,'-s',args.serial,'shell','-T','run-as',PACKAGE,'tee','files/'+name],input=data,stdout=subprocess.DEVNULL,check=True)
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for n in apk.namelist():
            if n.endswith('.proto') and ('/' not in n or n.startswith(('utils/','enums/'))):apk.extract(n,tmp)
        def parse(file,proto,data):
            return subprocess.run(['protoc','-I'+tmp,'-I/usr/include','--decode='+proto,file],
                                  input=data,capture_output=True,check=True).stdout
        with ZipFile(BOARD/filename) as src:
            router=parse('RouterRecord.proto','RouterRecord',src.read('lesson/p1/router.bin'))
            files=re.findall(rb'commandRecord \{\s+fileName: "(.*?)"',router)
        result={'input_sha256':hashlib.sha256((BOARD/filename).read_bytes()).hexdigest(),'apps':[]}
        reference=None
        for app,p in mappings.items():
            payload=(ROOT/'中育apk'/(app+'.apk')).read_bytes()
            put('art-variant.apk',payload)
            contents={**p,'count':str(count),'files':b','.join(files).decode()}
            put('art-variant.properties',''.join(k+'='+v+'\n' for k,v in contents.items()).encode())
            log=device('shell','am','instrument','-w','-e','artworkVariant','true',PACKAGE+'/.ProbeRun').decode()
            row=dict(app=app,apk_sha256=hashlib.sha256(payload).hexdigest(),symbols=p)
            if 'INSTRUMENTATION_CODE: -1' not in log:
                print(app,log,flush=True);row['error']=log
            else:
                snapshots=[]
                for name in [f'step-{i}' for i in range(count+1)]+['restored']:
                    wire=device('exec-out','run-as',PACKAGE,'cat','files/art-variant-result/'+name+'.bin')
                    snapshots.append(parse('GraphSnapshot.proto','PageSnapshot.GraphSnapshot',wire))
                row['decoded_snapshot_sha256']=[hashlib.sha256(w).hexdigest() for w in snapshots]
                if args.image:
                    image_matrices = [image_state(w) for w in snapshots]
                    expected = [[1,0,440,0,1,150,0,0,1],
                                [0,-1.5,591.25,1.5,0,111.75,0,0,1],
                                [0,-1.5,651.25,1.5,0,151.75,0,0,1]]
                    for actual, target in zip(image_matrices, [*expected,expected[-1]]):
                        assert all(abs(a-b)<(2 if i in (2,5) else .0001)
                                   for i,(a,b) in enumerate(zip(actual,target))), (app,actual)
                    row['image_matrices'] = image_matrices
                    row['replay_vs_restored_lines'] = list(difflib.unified_diff(
                        snapshots[-2].decode().splitlines(),snapshots[-1].decode().splitlines(),
                        fromfile='replayed',tofile='restored',n=1,lineterm=''))
                    assert not row['replay_vs_restored_lines'], (app,row['replay_vs_restored_lines'])
                if reference is None:reference=snapshots
                row['same_as_mistake']=[x==y for x,y in zip(reference,snapshots)]
                print(app,row['same_as_mistake'],flush=True)
            result['apps'].append(row)
        (ROOT/f'reports/evidence/art/artwork-{stem}-variants.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        assert all(row.get('same_as_mistake')==[True]*(count+2) for row in result['apps'])
if __name__=='__main__':main()
