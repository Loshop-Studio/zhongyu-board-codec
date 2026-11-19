"""Compare V6 paper edits with Android's recorder, player, note list and ObjectBox importer."""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image

from check_native_page_recording import ROOT, database, schema_reader


def members(path):
    with ZipFile(path) as archive:
        return {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}


def spans(row):
    indices = np.flatnonzero(row > .05)
    runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    return [(float(np.average(r, weights=row[r])), float(row[r].sum())) for r in runs
            if r.size and r[0] > 3 and r[-1] < len(row)-4]


def compare(web_file, android_file, paper, ink, screen=True):
    web = Image.open(web_file).convert('RGB')
    android = Image.open(android_file).convert('RGB')
    crop = None
    if screen:
        rgb = np.asarray(web)
        y, x = np.nonzero(np.all(rgb == paper, axis=2) | np.all(rgb == ink, axis=2))
        crop = tuple(map(int,(x.min(), y.min(), x.max()+1, y.max()+1)))
        assert abs((crop[2]-crop[0])/(crop[3]-crop[1]) - 4/3) < .005
        web = web.crop(crop).resize(android.size, Image.Resampling.LANCZOS)
    assert web.size == android.size
    def coverage(image):
        rgb = np.asarray(image, dtype=float)
        diff = np.asarray(ink) - paper
        return np.clip(((rgb-paper)*diff).sum(axis=2)/(diff@diff), 0, 1)
    w, a = coverage(web), coverage(android)
    result = {'browser_paper_crop': crop}
    # Sample two ink-free strips. An intersecting grid line is omitted from the
    # perpendicular strip so each run measures only a single paper line.
    for name, web_strip, native_strip in [('vertical', w[450:470], a[450:470]),
                                          ('horizontal', w.T[585:610], a.T[585:610])]:
        idx = np.argmin(native_strip.sum(axis=1))
        browser_lines, native_lines = spans(web_strip[idx]), spans(native_strip[idx])
        assert len(native_lines)==len(browser_lines),(web_file,name,browser_lines,native_lines)
        center = max((abs(x[0]-y[0]) for x,y in zip(browser_lines,native_lines)), default=0)
        width = max((abs(x[1]-y[1]) for x,y in zip(browser_lines,native_lines)), default=0)
        assert center < .6 and width < .65, (web_file,name,center,width)
        result[name] = dict(count=len(native_lines), max_center_error_px=round(center,4),
                            max_width_error_px=round(width,4))
    assert result['horizontal']['count'] >= 8
    return result


def db_paper(path):
    tables = {e['name']: e['rows'] for e in database(path)['entities']}
    page, = tables['PageEntity']
    head = next(h for h in tables['HeaderEntity'] if h['id']==page['headerEntityId'])
    style = next(s for s in tables['BackgroundLineConfigEntity'] if s['id']==head['lastBackgroundLineConfigId'])
    return dict(duration=head['duration'], color=head['lastBackgroundColor'], lines=style,
                commands=len(tables['CommandInfoEntity']), strokes=len(tables['TouchEventEntity']))


def verify(work):
    browser = work/'browser'
    src_path = work/'source/native-paper.zip'
    dst_path = browser/'web-paper.zip'
    original, edited, plain = map(members, [src_path,dst_path,browser/'plain.zip'])
    unchanged = src_path.read_bytes()
    assert (browser/'undone.zip').read_bytes() == (browser/'untouched.zip').read_bytes() == unchanged
    assert members(browser/'redone.zip') == members(browser/'cloud-paper.zip') == edited
    parse = schema_reader(ROOT/'中育apk/错题本.apk')
    entry, = parse('PageRouter',original['page_router.bin']).pageInfo
    prefix = entry.name + '/'
    def read(files,name):
        return files[prefix+name]
    orig = parse('Header',read(original,'header.bin'))
    h = parse('Header',read(edited,'header.bin'))
    origin_route = parse('RouterRecord',read(original,'router.bin'))
    clock, switches, cameras = 0, [], []
    for ref in origin_route.commandRecord:
        for c in parse('CommandSource', read(original,ref.fileName)).commandInfo:
            start = clock + (c.delayTime if c.isPlay else 0)
            if c.commandEnum == 9:
                style = parse('CommandSource.CommandInfo.Config', c.data).lastBackgroundLineConfig
                switches.append((start,style.lineType,style.lineSpace,style.lineWidth))
            if c.commandEnum == 7: cameras.append(start)
            clock = start + (c.duration if c.isPlay else 0)
    assert switches == [(177,0,32,2),(742,1,40,4)] and cameras == [773]
    assert h.duration == orig.duration == 1263
    assert h.lastBackgroundColor & 0xffffffff == 0xfff1f3fc
    assert (h.lastBackgroundLineConfig.lineType,h.lastBackgroundLineConfig.lineSpace,h.lastBackgroundLineConfig.lineWidth)==(0,24,0)
    assert not parse('Header',read(plain,'header.bin')).lastBackgroundLineConfig.lineColor
    assert {p for p in original if original[p] != edited[p]} == {prefix+n for n in ['header.bin','router.bin','screenshot.png']}
    created, = set(edited)-set(original)
    route = parse('RouterRecord',read(edited,'router.bin')).commandRecord[-1]
    assert created == prefix+route.fileName
    assert route.validate == hashlib.sha256(edited[created]).hexdigest().lstrip('0').zfill(32)
    command, = parse('CommandSource',edited[created]).commandInfo
    assert command.commandEnum==9 and not command.isPlay and command.duration==command.delayTime==0
    event=parse('CommandSource.CommandInfo.Config',command.data)
    assert event.lastBackground==event.originBackground==h.lastBackgroundColor
    assert event.originBackgroundLineConfig.lineType==1 and event.lastBackgroundLineConfig.lineType==0
    assert event.lastBackgroundLineConfig.lineWidth==3
    png=read(edited,'screenshot.png')
    decoded=Image.open(BytesIO(png)).convert('RGBA')
    assert decoded.tobytes()==Image.open(work/'edited-native/list.png').convert('RGBA').tobytes()
    lines=((242,247,253),(48,104,168))
    grid=((250,244,220),(49,131,117))
    purple=((241,243,252),(121,71,160))
    frames={}
    for t in (200,650,758,1010,1263,400):
        colors=lines if t in (200,650,400) else grid
        frames[str(t)]=compare(browser/f'seek-{t}.png',work/f'player/seek-{t}.png',*colors)
    assert Image.open(work/'player/seek-100.png').convert('RGBA').getchannel('A').getextrema()==(0,0)
    box=frames['200']['browser_paper_crop']
    empty=Image.open(browser/'seek-100.png').convert('RGB').crop((box[0]+2,box[1]+2,box[2]-2,box[3]-2))
    assert empty.getcolors(1)==[(empty.width*empty.height,(255,255,255))]
    plain_image=Image.open(BytesIO(read(plain,'screenshot.png'))).convert('RGB')
    assert np.all(np.asarray(plain_image)[350:,500:] == purple[0])
    plain_native=Image.open(work/'plain-native/grid.png').convert('RGB')
    assert np.all(np.asarray(plain_native)[350:,500:] == purple[0])
    assert plain_image.tobytes() == Image.open(work/'plain-native/list.png').convert('RGB').tobytes()
    for t in (200,1010):
        assert (Image.open(work/f'edited-player/seek-{t}.png').tobytes() ==
                Image.open(work/f'player/seek-{t}.png').tobytes())
    db_orig=db_paper(work/'cloud-original/page_mdb/web-import.mdb')
    db_edit=db_paper(work/'cloud-edited/page_mdb/web-import.mdb')
    assert db_orig['commands']==9 and db_edit['commands']==10
    assert db_edit['duration']==db_orig['duration']==1263 and db_edit['strokes']==db_orig['strokes']==2
    assert db_edit['lines']['lineSpace']==24 and db_edit['lines']['lineColor']==h.lastBackgroundLineConfig.lineColor
    assert db_edit['lines']['lineWidth']==db_orig['lines']['lineWidth']==3
    return dict(original_sha256=hashlib.sha256(unchanged).hexdigest(),edited_sha256=hashlib.sha256(dst_path.read_bytes()).hexdigest(),
                duration_ms=h.duration, recorded_config_ms=[s[0] for s in switches], recorded_camera_ms=cameras[0],
                original_bytes_after_undo=True, all_edited_members_equal_after_redo_and_cloud_export=True,
                native_list_png_identical_rgba=True, cleared_ruling_android_and_list=True,
                preserved_initial_playback_pixels=[200,1010],
                edited_members=sorted(n for n in original if original[n]!=edited[n]),new_member=created,
                browser_seek=json.loads((browser/'trace.json').read_text()), replay_ruling_pixels=frames,
                reopened_native_paper=compare(browser/'original-edit.png',work/'reopened/grid.png',*grid),
                edited_paper=compare(browser/'changed.png',work/'edited-native/grid.png',*purple),
                reopened_web_edit=compare(browser/'reopened.png',work/'edited-native/grid.png',*purple),
                last_replay_frame=compare(browser/'changed.png',work/'edited-player/seek-1263.png',*purple),
                saved_png=compare(BytesIO(png),work/'edited-native/opened.png',*purple,screen=False),
                cloud_source=db_orig,cloud_edited=db_edit)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('work', type=Path)
    print(json.dumps(verify(cli.parse_args().work),indent=2,ensure_ascii=False))
