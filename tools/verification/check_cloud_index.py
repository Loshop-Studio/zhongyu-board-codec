"""Compare browser output, both native readbacks and the published offline decoders."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from cloud_note import inspect


def check(source,web,created,reopened,database):
    def members(note):
        with ZipFile(note) as z: return {n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    def decode(*args):
        return json.loads(subprocess.check_output([sys.executable,ROOT/'tools/read-data.py',*args]))
    original,edited=members(source),members(web)
    assert original.keys()==edited.keys()
    changes=[n for n in edited if edited[n]!=original[n]]
    assert changes==['课堂本/第2页/actions.bin']
    native=json.loads(created.read_bytes())
    reread=json.loads(reopened.read_bytes())
    for raw,doc in ((native,original),(reread,edited)):
        assert raw['members_sha256']=={p:hashlib.sha256(b).hexdigest() for p,b in doc.items()}
    index=decode('--type','cloud-note',source)['notes'][0]
    assert decode('--type','cloud-note',web)['notes']==[index]
    assert [p['android_path'] for p in index['pages']]==native['index']
    assert [p['directory'] for p in index['pages'] if p['present']]==native['editor_pages']==reread['editor_pages']
    assert [(r['local'],r['service']) for r in index['resources']]==[(r['local'],r['service']) for r in native['resources']]
    assert all(r['present'] for r in index['resources'])
    assert index['unlisted_sketch_pages']==['unlisted']
    for record, counts in ((native, [2,1,2]), (reread, [3,1,3])):
        assert [int(record['mistake_sketch'][p].split('strokes=')[1]) for p in record['editor_pages']] == counts
        assert all('makeExtensionsImmutable' in record['cloud_sketch'][p] for p in record['editor_pages'])
    marked=str(Path(native['index'][0]).parent.parent/'marker-check')
    info=decode('--type','cloud-note-room','--deleted-page',marked,database)['notes'][0]
    bare=decode('--type','cloud-note-room',database)['notes'][0]
    assert info['row_count']==8 and info['deleted_rows']==1
    assert [p['representative'] for p in info['pages']]==native['room_representatives']==native['representatives']
    assert [p['preview'] for p in info['pages']]==native['previews']
    assert len(bare['pages'])==native['representatives_after_restore']==3
    assert info['legacy_source'] == 'ResourceEntity'
    assert info['legacy_editor_pages'] == bare['legacy_editor_pages']
    assert [Path(p['page']).name for p in info['legacy_editor_pages']] == native['editor_with_room'] == reread['editor_with_room']
    assert [p['index'] for p in bare['pages']] == [0,2,2]
    assert [p['index'] for p in bare['legacy_editor_pages']] == [0,2,4]
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        schema={k:db.execute('PRAGMA '+k).fetchone()[0] for k in ['user_version','integrity_check']}
        assert schema['integrity_check']=='ok'
    fixture={'index.json':b'["/old/a","/new/a","/new/empty"]','res.json':b'[{"local":"/new/a/actions.bin","service":"fixture"}]','a/actions.bin':b''}
    note=inspect(set(fixture),fixture.__getitem__,['empty/'])['notes'][0]
    assert note['android_base']=='/new/' and [p['present'] for p in note['pages']]==[False,True,True]
    assert note['pages'][-1]['sketch'] is None
    return {'cloud_original_sha256':native['apk_sha256'],'mistake_original_sha256':hashlib.sha256((ROOT/'中育apk/错题本.apk').read_bytes()).hexdigest(),
            'input_zip_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'browser_zip_sha256':hashlib.sha256(web.read_bytes()).hexdigest(),
            'changed_members':changes,'index':index,'native_before':native,'native_after':reread,
            'database':{'sha256':hashlib.sha256(database.read_bytes()).hexdigest(),**schema,'without_marker':bare,'with_marker':info}}
if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for arg in ['source','web','created','reopened','database']:cli.add_argument(arg,type=Path)
    print(json.dumps(check(**vars(cli.parse_args())),ensure_ascii=False,indent=2))
