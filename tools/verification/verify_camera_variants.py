"""Read each final and in-progress V6 camera from the five original DEX schedulers."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from check_native_page_recording import ROOT, from_zip, schema_reader
from verify_cursor_variants import run_variant_seeks

IDENTITY=[1,0,0,0,1,0,0,0,1]

def matrix(m):
    return [m.scaleX,m.skewX,m.transX,m.skewY,m.scaleY,m.transY,m.perSp0,m.perSp1,m.perSp2]

def product(a,b):
    return [sum(a[3*r+k]*b[3*k+c] for k in range(3)) for r in range(3) for c in range(3)]

def camera_commands(note):
    files=from_zip(note)
    parse=schema_reader(ROOT/'中育apk/错题本.apk')
    entry,=parse('PageRouter',files['page_router.bin']).pageInfo
    start=entry.name+'/'
    items={n[len(start):]:data for n,data in files.items() if n.startswith(start)}
    def read(kind,n): return parse(kind,items[n])
    meta=read('Header','header.bin')
    router=read('RouterRecord','router.bin')
    clock=0
    actions=[]
    for ref in router.commandRecord:
        for c in read('CommandSource',ref.fileName).commandInfo:
            begin=clock+(c.delayTime if c.isPlay else 0)
            if c.isPlay: clock=begin+c.duration
            if c.commandEnum not in (7,8): continue
            info=parse('CommandSource.CommandInfo.'+('Camera' if c.commandEnum==7 else 'CameraMatrix'),c.data)
            row={'start':begin,'end':clock,'origin':matrix(info.originMatrix),'last':matrix(info.lastMatrix),'samples':[]}
            if c.commandEnum==8:
                seq=read('MatrixSource',info.sourceFileName).matrixInfo[info.sourceId].matrix
                assert seq and all(x.eventTime<=y.eventTime for x,y in zip(seq,seq[1:]))
                for m in seq:
                    row['samples'].append({'ms':begin+m.eventTime-seq[0].eventTime,'delta':matrix(m)})
                assert all(math.isclose(x,y,abs_tol=.0001) for x,y in zip(product(matrix(seq[-1]),row['origin']),row['last']))
            actions.append(row)
    assert actions[-1]['last']==matrix(read('PageSnapshot','snapshot.bin').cameraMatrix)
    return items,meta.duration,actions

def current(actions,ms):
    base=IDENTITY
    for a in actions:
        if ms<a['start']: break
        if ms>=a['end']:
            base=a['last']
            continue
        reached=[x['delta'] for x in a['samples'] if x['ms']<=ms]
        if len(reached)>1 or len(a['samples'])==1 and reached: return product(reached[-1],base)
        break
    return base

def native_symbols(app,conf):
    root=ROOT/'android'/app
    def methods(file):
        return re.findall(r'^\.method [^\n]*? ([^\s]+\([^\s]*)\n(.*?)^\.end method',file.read_text(),re.M|re.S)
    adapter,=subprocess.check_output(['rg','-l','-F','--glob','*.smali','MatrixAdapter cameraMatrixConcat=',str(root)],text=True).splitlines()
    concat,= [body for _,body in methods(Path(adapter)) if 'MatrixAdapter cameraMatrixConcat=' in body]
    field=re.search(r'iget-object [^\n]+?->([^:]+):Landroid/graphics/Matrix;',concat)[1]
    controller,=root.glob('smali*/'+conf['control'].replace('.','/')+'.smali')
    changing,=[sig.split('(')[0] for sig,body in methods(controller) if sig.endswith('(Landroid/graphics/Matrix;)V') and '->postConcat(' in body]
    return {'cameraField':field,'cameraChanging':changing}

def check(serial,note):
    items,duration,actions=camera_commands(note)
    times=sorted({0,duration,*[a['end'] for a in actions],
        *[x['ms']+1 for a in actions for x in a['samples'] if x['ms']+1<a['end']]})
    times.append(actions[1]['samples'][2]['ms']+1)
    reports=run_variant_seeks(serial,items,duration,times,'camera',native_symbols)
    for app in reports:
        for t,row in zip(times,app['states'],strict=True):
            want=current(actions,t)
            assert t==row['ms'] and all(math.isclose(a,b,abs_tol=.0002) for a,b in zip(want,row['matrix'],strict=True)),(app['app'],t,want,row)
    return {'input_sha256':hashlib.sha256(note.read_bytes()).hexdigest(),'duration_ms':duration,
            'checkpoints_per_app':len(times),'actions':actions,'apps':reports}

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('serial');cli.add_argument('note',type=Path);cli.add_argument('output',type=Path)
    args=cli.parse_args()
    args.output.write_text(json.dumps(check(args.serial,args.note),ensure_ascii=False,indent=2)+'\n')
