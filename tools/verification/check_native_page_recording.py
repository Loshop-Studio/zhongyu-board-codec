"""Check the V6 Android → Chromium → Android save cycle against original APK schemas."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from PIL import Image, ImageChops
from compare_sketch_render import count, paper_rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from objectbox_store import decode as database


def digest(data):
    return hashlib.sha256(data).hexdigest()


def package(folder, dest):
    with ZipFile(dest, 'w') as out:
        for member in sorted(p for p in folder.rglob('*') if p.is_file()):
            out.writestr(ZipInfo(member.relative_to(folder).as_posix()), member.read_bytes(),
                         compress_type=ZIP_DEFLATED)


def schema_reader(apk, roots=('Command.proto','Source.proto','Header.proto','PageRouter.proto','RouterRecord.proto','GraphSnapshot.proto')):
    with tempfile.TemporaryDirectory() as temp, ZipFile(apk) as z:
        dest = Path(temp)/'types.pb'
        for member in z.namelist():
            if member.endswith('.proto') and ('/' not in member or member.startswith(('utils/','enums/'))):
                z.extract(member,temp)
        subprocess.run(['protoc','-I'+temp,'-I/usr/include','--include_imports','--descriptor_set_out='+str(dest),
                        *roots],
                       capture_output=True,check=True)
        pool = descriptor_pool.DescriptorPool()
        for desc in descriptor_pb2.FileDescriptorSet.FromString(dest.read_bytes()).file:
            pool.Add(desc)
    def parse(name,data):
        return message_factory.GetMessageClass(pool.FindMessageTypeByName(name)).FromString(data)
    return parse


def pages(files, parse):
    assert 'header.bin' not in files
    results=[]
    for entry in parse('PageRouter',files['page_router.bin']).pageInfo:
        def data(name):
            return files[entry.name+'/'+name]
        header=parse('Header',data('header.bin'))
        routes=parse('RouterRecord',data('router.bin'))
        snapshot=parse('PageSnapshot',data('snapshot.bin')).graphSnapshot
        commands=[]
        touches={}
        for key in ('commandRecord','touchSourceRecord'):
            for ref in getattr(routes,key):
                raw=data(ref.fileName)
                assert ref.validate==digest(raw).lstrip('0').zfill(32)
                if key=='commandRecord':
                    commands.extend(parse('CommandSource',raw).commandInfo)
                else:
                    touches[ref.fileName]=parse('TouchSource',raw).touchInfo
        strokes=[]
        def visit(g):
            if g.sourceFileName in touches:
                item=touches[g.sourceFileName][g.sourceId]
                points=[[p.x,p.y] for p in item.touchEvent]
                strokes.append({'points':points,'argb':item.paint.color&0xffffffff,
                                'width':item.paint.width,'style':item.paint.style})
            for child in g.childGraph:
                visit(child)
        visit(snapshot)
        clock=0
        timeline=[]
        for cmd in commands:
            start=clock+(cmd.delayTime if cmd.isPlay else 0)
            if cmd.isPlay:
                clock=start+cmd.duration
            row={'command':cmd.commandEnum,'is_play':cmd.isPlay,'start':start,'end':clock,'delay':cmd.delayTime,'duration':cmd.duration}
            if cmd.commandEnum==1:
                g=parse('CommandSource.CommandInfo.GraphData',cmd.data)
                if g.sourceFileName in touches:
                    events=touches[g.sourceFileName][g.sourceId].touchEvent
                    row['touch_offset_ms']=[p.eventTime-events[0].eventTime for p in events]
            timeline.append(row)
        results.append({'name':entry.name, 'version':header.version, 'size':[header.width,header.height],
                        'duration_ms':header.duration,'strokes':strokes,'timeline':timeline})
    return results


def from_zip(path):
    with ZipFile(path) as z:
        return {f.filename:z.read(f) for f in z.infolist() if not f.is_dir()}


def compare_pixels(native, browser, extra=False):
    screenshot=Image.open(browser).convert('RGB')
    crop=paper_rectangle(screenshot)
    web=screenshot.crop(crop).resize((640,480),Image.Resampling.LANCZOS)
    image=Image.open(native).convert('RGBA')
    assert image.size==(641,481)
    paper=Image.new('RGBA',(640,480),'white')
    paper.alpha_composite(image.crop((0,0,640,480)))
    def masks(im):
        r,g,b=im.convert('RGB').split()
        # Each pen occupies a disjoint region. Isolate it before thresholding so
        # antialiasing on the dark third stroke cannot affect the green mask.
        out=[ImageChops.subtract(x,y).crop(region).point(lambda v:255 if v>=25 else 0)
             for x,y,region in ((g,r,(0,0,310,170)),(r,g,(300,170,480,260)))]
        if extra:
            out.append(im.convert('L').crop((120,255,440,420)).point(lambda v:255 if v<125 else 0))
        return out
    result=[]
    for name,a,b in zip(('green','red','web stroke'),masks(paper),masks(web)):
        shared=count(ImageChops.darker(a,b)); union=count(ImageChops.lighter(a,b))
        assert union and shared/union>.90 and max(abs(p-q) for p,q in zip(a.getbbox(),b.getbbox()))<=1,(name,shared,union)
        result.append({'stroke':name,'native_pixels':count(a),'browser_pixels':count(b),'shared':shared,
                       'union':union,'intersection_over_union':shared/union})
    return result


def verify(work, proof):
    apk=ROOT/'中育apk/错题本.apk'
    original=proof/'native-v6-recording.zip'
    browser=work/'browser'
    initial=from_zip(original)
    assert initial=={p.relative_to(work/'note').as_posix():p.read_bytes() for p in (work/'note').rglob('*') if p.is_file()}
    assert (browser/'untouched.zip').read_bytes()==(browser/'undone.zip').read_bytes()==original.read_bytes()
    edited=from_zip(browser/'web-native-v6.zip')
    assert edited==from_zip(browser/'web-native-v6-cloud.zip')
    returned=work/'returned/note'
    final={p.relative_to(returned).as_posix():p.read_bytes() for p in returned.rglob('*') if p.is_file()}
    parse=schema_reader(apk)
    recorded,=pages(initial,parse)
    browser_page,=pages(edited,parse)
    native_page,=pages(final,parse)
    assert recorded['size']==[640,480] and recorded['version']==6
    a,b,c=(p['strokes'] for p in [recorded,browser_page,native_page])
    assert len(a)==2 and len(b)==3 and len(c)==4 and c[:3]==b and b[:2]==a
    assert [s['points'] for s in a]==[[[80,74],[120,88],[166,143],[202,92],[232,107]],
                                      [[330,220],[365,200],[399,252],[432,232]]]
    assert c[3]['points']==[[480,260],[510,285],[525,260],[556,285]]
    assert [p['duration_ms'] for p in [recorded,browser_page,native_page]]==[recorded['duration_ms']]*3
    for shard in initial:
        if shard.endswith(('_command.bin','_touch.bin')):
            assert initial[shard]==edited[shard]==final[shard]
    assert browser_page['timeline'][:6]==native_page['timeline'][:6]==recorded['timeline']
    assert [r['command'] for r in recorded['timeline']]==[1,1,1,1,1,10]
    for row in (browser_page['timeline'][-1],native_page['timeline'][-1]):
        assert not row['is_play'] and row['touch_offset_ms'][-1]==row['duration'] and row['duration']>0
    assert max(browser_page['timeline'][-1]['touch_offset_ms'])>=80
    assert browser_page['timeline'][-1]['end']==native_page['timeline'][-1]['end']==recorded['duration_ms']
    for row in recorded['timeline']:
        if 'touch_offset_ms' in row: assert row['touch_offset_ms'][-1]==row['end']-row['start']
    two=pages(from_zip(browser/'web-native-v6-two-pages.zip'),parse)
    assert two[0]==browser_page and len(two)==2 and not two[1]['strokes'] and two[1]['duration_ms']==0

    db=database(work/'cloud/page_mdb/web-import.mdb')
    tables={e['name']:e for e in db['entities']}
    db_pages=tables['PageEntity']['rows']
    roots={p['recordEntityId']:p['dirName'] for p in db_pages}
    def linked(table,child):
        pairs={a:[] for a in (row['id'] for row in tables[table]['rows'])}
        for a,b in next(rel['pairs'] for rel in tables[table]['relations'] if rel['target_entity']==child):
            pairs[a].append(b)
        return pairs
    linked_events=linked('TouchRecordEntity','TouchEventEntity')
    linked_points=linked('TouchEventEntity','TouchInfoEntity')
    by_id={row['id']:row for row in tables['TouchInfoEntity']['rows']}
    found={name:[] for name in roots.values()}
    for shard in tables['TouchRecordEntity']['rows']:
        for event in sorted(linked_events[shard['id']]):
            found[roots[shard['recordId']]].append([[by_id[i]['x'],by_id[i]['y']] for i in sorted(linked_points[event])])
    for p in two:
        assert found[p['name']]==[s['points'] for s in p['strokes']]
    all_counts={k:len(tables[k]['rows']) for k in ['PageEntity','CommandInfoEntity','TouchEventEntity','TouchInfoEntity','AudioInfoEntity']}
    shot=next(data for name,data in initial.items() if name.endswith('/screenshot.png'))
    assert shot==(work/'android.png').read_bytes()
    final_zip=proof/'android-resaved-v6.zip'
    assert from_zip(final_zip)==final
    assert (browser/'resaved-unchanged.zip').read_bytes()==final_zip.read_bytes()
    return {'android_resave_sha256':digest(final_zip.read_bytes()),'web_reopened_four_strokes':True,
            'two_page_archive_sha256':digest((browser/'web-native-v6-two-pages.zip').read_bytes()),
            'cloud_import_mdb_sha256':digest((work/'cloud/page_mdb/web-import.mdb').read_bytes()),
            'apk_sha256':digest(apk.read_bytes()),'members':[{'name':k,'sha256':digest(v)} for k,v in initial.items()],
            'original_archive_sha256':digest(original.read_bytes()),'edited_archive_sha256':digest((browser/'web-native-v6.zip').read_bytes()),
            'returned_original_shards_preserved':True,'original_and_undone_archives_identical':True,
            'original_page':recorded,'web_stroke':browser_page['timeline'][-1],'native_added_stroke':native_page['timeline'][-1],
            'page_durations_ms':[p['duration_ms'] for p in (recorded,browser_page,native_page)],'stroke_counts':[len(a),len(b),len(c)],'point_counts_after_android_resave':[len(s['points']) for s in c],
            'original_pixels':compare_pixels(work/'android.png',browser/'browser-native.png'),
            'reopened_web_edit_pixels':compare_pixels(work/'returned/opened.png',browser/'browser-edit.png',True),
            'cloud_database_counts':all_counts,'cloud_coordinates_match':True,'page_dimensions':[p['size'] for p in two]}


if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('capture_directory',type=Path)
    args.add_argument('--pack-original',action='store_true',help='Package a fresh Android recording before running the browser check')
    opt=args.parse_args()
    proof=ROOT/'reports/evidence/board'
    if opt.pack_original:
        package(opt.capture_directory/'note',proof/'native-v6-recording.zip')
    else:
        print(json.dumps(verify(opt.capture_directory,proof),indent=2,ensure_ascii=False))
