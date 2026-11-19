"""Compare native cursor recording, Flutter playback, the original player and ObjectBox import."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

from check_native_page_recording import database, from_zip, schema_reader, ROOT
from compare_sketch_render import paper_rectangle
from verify_cursor_variants import expected, gestures


def load_screen(file, web):
    im = Image.open(file).convert('RGB')
    if not web:
        assert im.size==(640,480)
        return np.asarray(im,dtype=int), None
    box=paper_rectangle(im)
    assert abs((box[2]-box[0])/(box[3]-box[1])-4/3)<.007
    return np.asarray(im.crop(box).resize((640,480),Image.Resampling.LANCZOS),dtype=int), box


def mask(rgb,color):
    target=np.array([(color>>16)&255,(color>>8)&255,color&255])
    return np.max(np.abs(rgb-target),axis=2)<45


def center(mask):
    ys,xs = np.nonzero(mask)
    return np.array([xs.mean()+.5,ys.mean()+.5])


def compare(native,browser,want,colors):
    a,_=load_screen(native,False)
    b,box=load_screen(browser,True)
    measured={}
    for color in colors:
        left,right=mask(a,color),mask(b,color)
        if not want or color!=want['color']:
            assert not left.any() and not right.any(),(native,browser,color)
            continue
        assert left.any() and right.any()
        ac,bc=center(left),center(right)
        error=float(np.linalg.norm(ac-bc))
        delta=float(np.linalg.norm(ac-[want['x'],want['y']]))
        iou=float((left&right).sum()/(left|right).sum())
        assert error<.9 and delta<.9 and iou>.80,(native,browser,want,ac,bc,iou)
        measured.update(center_android=ac.round(3).tolist(),center_web=bc.round(3).tolist(),
                        center_delta_px=round(error,3),overlap=round(iou,4))
    return dict(web_crop=box,**measured)


def check(work):
    web=work/'release-browser'
    original=work/'native.zip'
    edited=web/'web.zip'
    files,duration,cursors=gestures(edited)
    old,old_duration,existing=gestures(original)
    assert old_duration==2011 and len(cursors)==4 and cursors[:2]==existing
    assert [c['start'] for c in cursors[2:]]==[old_duration,cursors[2]['end']+64]
    assert duration==cursors[-1]['end']+64
    assert set(old)<=set(files)
    assert {name for name in old if old[name]!=files[name]}=={'header.bin','router.bin'}
    new_names=set(files)-set(old)
    assert len(new_names)==4 and sum(n.endswith('_touch.bin') for n in new_names)==2 and sum(n.endswith('_command.bin') for n in new_names)==2
    assert (web/'undone.zip').read_bytes()==(web/'original.zip').read_bytes()==original.read_bytes()
    assert (web/'cancelled.zip').read_bytes()==(web/'mouse.zip').read_bytes()
    trace=json.loads((web/'trace.json').read_bytes())
    variants=json.loads((work/'release-variants.json').read_bytes())
    digest=hashlib.sha256(edited.read_bytes()).hexdigest()
    assert len(variants['apps'])==5 and variants['input_sha256']==digest
    colors={c['color'] for c in cursors}
    samples=[]
    for rows,android,prefix,cs in [(trace['trace'],work/'play','seek-',existing),(trace['edited'],work/'release-player','edited-',cursors)]:
        for row in rows:
            t=row['target']
            result=compare(android/f'seek-{t}.png',web/f'{prefix}{t}.png',expected(cs,t),colors)
            samples.append(dict(edited=prefix=='edited-',target=t,displayed=row['displayed'],**result))
    compare(work/'release-player'/f'seek-{duration}.png',web/'ended.png',None,colors)

    # The UI test touches these CSS coordinates. Verify the live marker and
    # the subsequent wire samples separately from playback.
    live=[]
    for i,(tool,position,offset) in enumerate([('mouse',(425,418),0),('finger',(450,495),50)]):
        image,box=load_screen(web/(tool+'-live.png'),True)
        xy=center(mask(image,cursors[2+i]['color']))
        touch=(np.array(position)-box[:2])*[640/(box[2]-box[0]),480/(box[3]-box[1])]
        point=cursors[2+i]['points'][1]
        assert np.linalg.norm(xy - (touch-[0,offset])) < 1
        assert np.linalg.norm(xy-[point['x'],point['y']]) < .9
        live.append(dict(input=tool,screen_input=list(position),page_contact=touch.round(3).tolist(),
                         live_center=xy.round(3).tolist(),offset_y_px=offset))

    # Check every point of every original or appended touch shard after the
    # cloud APK has imported them into its relational ObjectBox model.
    parse=schema_reader(ROOT/'中育apk/错题本.apk')
    table={t['name']:t for t in database(work/'release-cloud/page_mdb/web-import.mdb')['entities']}
    def linked(name,target):
        groups=defaultdict(list)
        for a,b in next(r['pairs'] for r in table[name]['relations'] if r['target_entity']==target):groups[a].append(b)
        return groups
    events=linked('TouchRecordEntity','TouchEventEntity')
    points=linked('TouchEventEntity','TouchInfoEntity')
    touches={r['id']:r for r in table['TouchEventEntity']['rows']}
    pos={r['id']:r for r in table['TouchInfoEntity']['rows']}
    for record in table['TouchRecordEntity']['rows']:
        src=parse('TouchSource',files[record['fileName']])
        for event,info in zip(sorted(events[record['id']]),src.touchInfo,strict=True):
            assert [touches[event][n] for n in ('width','color','style')]==[info.paint.width,info.paint.color,info.paint.style]
            for ident,data in zip(sorted(points[event]),info.touchEvent,strict=True):
                row=pos[ident]
                assert (row['x'],row['y'],row['eventTime'])==(data.x,data.y,data.eventTime)
    route=parse('RouterRecord',files['router.bin'])
    wire=[c for ref in route.commandRecord for c in parse('CommandSource',files[ref.fileName]).commandInfo]
    db_commands=table['CommandInfoEntity']['rows']
    assert len(db_commands)==len(wire)==11 and len(touches)==5 and len(pos)==21
    for row,c in zip(db_commands,wire,strict=True):
        assert [row[n] for n in ('commandEnum','duration','isPlay','delayTime')]==[c.commandEnum,c.duration,c.isPlay,c.delayTime]
        assert bytes.fromhex((row['data'] or {}).get('hex',''))==c.data
    assert table['HeaderEntity']['rows'][0]['duration']==duration
    forward,still,ended=[load_screen(work/'forward'/(n+'.png'),False)[0] for n in ['paused','still','ended']]
    assert np.array_equal(forward,still)
    assert mask(forward,existing[0]['color'])[145,225]
    assert not any(mask(ended,c).any() for c in colors)
    web_pause,web_still,web_end=[load_screen(work/'forward-web'/(n+'.png'),False)[0] for n in ['paused','still','ended']]
    assert np.array_equal(web_pause,web_still) and mask(web_pause,cursors[2]['color']).any()
    assert not any(mask(web_end,c).any() for c in colors)
    assert [c.commandEnum for c in wire[-4:]]==[11,10,11,10]
    assert all(c.delayTime==64 and c.duration==0 and c.isPlay for c in (wire[-3],wire[-1]))
    return dict(web_forward_pause_matching_pixels=True,web_forward_terminal_clear=True,stop_delay_ms=64,native_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),web_sha256=digest,
                duration_before_ms=old_duration,duration_after_ms=duration,gestures=cursors,
                native_forward_pause_matching_pixels=True,pause_checked_ms=250,flutter_pause_position_ms=trace['frozen'][0],
                stable_preview_and_snapshot=True,undo_exact_zip=True,multitouch_cancel_exact_zip=True,
                changed_existing_members=['header.bin','router.bin'],new_members=sorted(new_names),
                live_web=live,checks=samples,terminal_cursor_absent=True,
                native_variants=len(variants['apps']),native_checkpoints_per_variant=variants['checkpoint_count'],
                objectbox=dict(commands=len(wire),touch_groups=len(touches),points=len(pos),all_points_and_commands_match=True))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('work',type=Path)
    print(json.dumps(check(cli.parse_args().work),ensure_ascii=False,indent=2))
