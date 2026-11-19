"""Compare camera timing, native frames, ZIP edits and all imported ObjectBox matrix values."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from check_native_page_recording import ROOT,database,from_zip,schema_reader
from compare_sketch_render import paper_rectangle
from verify_camera_variants import camera_commands,matrix

PEN=[22,111,100]
FIELDS=('scaleX','skewX','transX','skewY','scaleY','transY','perSp0','perSp1','perSp2')

def near(a,b):
    return all(math.isclose(x,y,abs_tol=.0002) for x,y in zip(a,b,strict=True))

def ink(file,box=None):
    im=Image.open(file).convert('RGB')
    if box:
        im=im.crop(box)
    mask=Image.fromarray(np.all(np.asarray(im)==PEN,axis=2))
    if box:
        mask=mask.resize((640,480),Image.Resampling.NEAREST)
    assert mask.size==(640,480)
    return np.asarray(mask)

def compare(pixels,reference):
    assert pixels.any() and reference.any()
    def center(a): return np.asarray(np.where(a)).mean(axis=1)[::-1]+.5
    return {'overlap':round(float((pixels&reference).sum()/(pixels|reference).sum()),4),
            'center_delta_px':round(float(np.linalg.norm(center(pixels)-center(reference))),3),
            'web_pixels':int(pixels.sum()),'android_pixels':int(reference.sum())}

def verify(work):
    web=work/'browser'
    base=ROOT/'reports/evidence/board/camera/native.zip'
    for name in ('undo.zip','pen-undo.zip','cancelled.zip'):
        assert (web/name).read_bytes()==base.read_bytes()
    note=web/'web.zip'
    assert (web/'reopened.zip').read_bytes()==note.read_bytes()
    old,old_ms,native=camera_commands(base)
    items,duration,actions=camera_commands(note)
    assert native==actions[:3] and len(actions)==5 and duration==actions[-1]['end']+192
    assert actions[3]['start']==old_ms and actions[4]['start']==actions[3]['end']+192
    assert all(a['delta'][0]==1 for a in native[1]['samples']) and native[2]['samples'][1]['delta'][0]>1.36
    assert len(native[1]['samples'])==5 and len(native[2]['samples'])==4
    assert all(a['delta'][0]==1 for a in actions[3]['samples']) and max(a['delta'][0] for a in actions[4]['samples'])>1.5
    writing_items,_,writing=camera_commands(web/'writing.zip')
    assert writing[:3]==native and len(writing)==4 and all(a['delta'][0]==1 for a in writing[3]['samples'])
    assert any(a['delta'][2]!=0 for a in writing[3]['samples'])
    parse=schema_reader(ROOT/'中育apk/错题本.apk')
    def strokes(items):
        root=parse('PageSnapshot',items['snapshot.bin']).graphSnapshot
        def walk(g):
            return int(bool(g.sourceFileName and g.sourceFileName.endswith('_touch.bin'))) + sum(walk(x) for x in g.childGraph)
        return walk(root)
    late,_,_=camera_commands(web/'late-second-touch.zip')
    assert [strokes(v) for v in (old,items,writing_items,late)]==[1,1,1,2]
    old_snapshot=parse('PageSnapshot',old['snapshot.bin'])
    new_snapshot=parse('PageSnapshot',items['snapshot.bin'])
    assert old_snapshot.graphSnapshot==new_snapshot.graphSnapshot
    changed=[k for k in old if old[k]!=items[k]]
    assert set(changed)<= {'router.bin','header.bin','snapshot.bin','screenshot.png'} and old.keys()<=items.keys()
    extra=sorted(items.keys()-old.keys())
    assert len(extra)==4 and sum(k.endswith('_matrix.bin') for k in extra)==2
    for report,file in [('variants.json','web.zip'),('writing-variants.json','writing.zip')]:
        result=json.loads((work/report).read_bytes())
        assert result['input_sha256']==hashlib.sha256((web/file).read_bytes()).hexdigest() and len(result['apps'])==5
    database_rows={t['name']:t for t in database(work/'cloud/page_mdb/web-import.mdb')['entities']}
    def related(source,target):
        pairs=next(r['pairs'] for r in database_rows[source]['relations'] if r['target_entity']==target)
        out=defaultdict(list)
        for x,y in pairs: out[x].append(y)
        return out
    groups=related('MatrixRecordEntity','MatrixEventEntity')
    children=related('MatrixEventEntity','MatrixInfoEntity')
    values={v['id']:v for v in database_rows['MatrixInfoEntity']['rows']}
    count=0
    for rec in database_rows['MatrixRecordEntity']['rows']:
        messages=parse('MatrixSource',items[rec['fileName']]).matrixInfo
        for info,event in zip(messages,groups[rec['id']],strict=True):
            for m,row_id in zip(info.matrix,children[event],strict=True):
                row=values[row_id]
                assert row['eventTime']==m.eventTime and [row[f] for f in FIELDS]==matrix(m)
                count+=1
    assert count==len(values)==sum(len(a['samples']) for a in actions)
    records=parse('RouterRecord',items['router.bin']).commandRecord
    wire=[c for r in records for c in parse('CommandSource',items[r.fileName]).commandInfo]
    rows=database_rows['CommandInfoEntity']['rows']
    for c,row in zip(wire,rows,strict=True):
        assert (row['commandEnum'],row['isPlay'],row['delayTime'],row['duration'])==(c.commandEnum,c.isPlay,c.delayTime,c.duration)
        assert bytes.fromhex((row['data'] or {}).get('hex',''))==c.data
    assert database_rows['HeaderEntity']['rows'][0]['duration']==duration
    trace=json.loads((web/'trace.json').read_bytes())
    box=paper_rectangle(Image.open(web/'native-650.png').convert('RGB'))
    samples=[]
    for group,prefix,sub,direct,data in [('original','native','forward','direct',native),('edited','edited','forward-web','direct-web',actions)]:
        folder=work/sub
        clock=json.loads((folder/'times.json').read_bytes())
        assert near(clock['ended']['matrix'],data[-1]['last']) and near(clock['settled']['matrix'],data[-1]['last'])
        for sample in trace[group]:
            target=sample['target']
            browser=ink(web/f'{prefix}-{target}.png',box)
            natural=ink(folder/f'forward-{target}.png')
            seek=ink(work/direct/f'seek-{target}.png')
            samples.append({'document':group,**sample,'android_clock':clock[str(target)]['clock'],
              'forward':compare(browser,natural),'direct':compare(browser,seek)})
    # The native moving layer contains only ink visible at gesture start. Its
    # entire image, including brush widths, follows the transient matrix.
    for sample in trace['edited'][1:3]:
        frame=next(s for s in samples if s['document']=='edited' and s['target']==sample['target'])
        assert frame['forward']['overlap']>.78,frame
    # Compare natural playback, direct seek and the actual recording end separately.
    last=trace['edited'][-2]['target']
    browser=ink(web/f'edited-{last}.png',box)
    terminal=compare(browser,ink(work/'forward-web/ended.png'))
    terminal_seek=compare(browser,ink(work/'direct-web'/f'seek-{duration}.png'))
    assert terminal['overlap']>.72 and terminal_seek['overlap']>.72,(terminal,terminal_seek)
    assert np.array_equal(ink(work/'forward-web/ended.png'),ink(work/'forward-web/settled.png'))
    return {'native_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'web_sha256':hashlib.sha256(note.read_bytes()).hexdigest(),
            'native_duration_ms':old_ms,'web_duration_ms':duration,'web_stop_delay_ms':192,
            'native_writing_pan_samples':len(native[1]['samples']),'native_viewing_pinch_samples':len(native[2]['samples']),
            'web_camera_sample_counts':[len(g['samples']) for g in actions[3:]],
            'original_files_changed':changed,'new_members':extra,'graph_snapshot_unchanged':True,
            'undo_cancel_and_reopen_byte_exact':True,'writing_fast_second_contact_strokes':1,'writing_late_second_contact_strokes':2,
            'objectbox':{'matrix_records':len(groups),'matrix_events':len(children),'samples':count,'commands':len(rows),'values_match':True},
            'web_crop':box,'pixel_comparisons':samples,'natural_end':terminal,'direct_end':terminal_seek,'settled_ms':250}

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('work',type=Path)
    print(json.dumps(verify(cli.parse_args().work),ensure_ascii=False,indent=2))
