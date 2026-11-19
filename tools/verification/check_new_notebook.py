"""Trace both browser-created pages through command chunks into the cloud-note database."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from objectbox_store import decode


def verify(archive, database):
    decoded=decode(database)
    tables={t['name']:t['rows'] for t in decoded['entities']}
    many={(t['name'],rel['target_entity']):rel['pairs'] for t in decoded['entities'] for rel in t['relations']}
    def targets(parent, owner, child):
        ids={b for a,b in many[parent,child] if a==owner}
        return sorted((r for r in tables[child] if r['id'] in ids),key=lambda r:r['id'])
    pages=sorted(tables['PageEntity'],key=lambda p:p['id'])
    assert [p['dirName'] for p in pages]==['p1','p2']
    def linked(table,owner):
        return sorted((r for r in tables[table] if r['recordId']==owner),key=lambda r:r['id'])
    with ZipFile(archive) as z:
        results=[]
        for page in pages:
            name=page['dirName'];owner=page['recordEntityId']
            header=next(r for r in tables['HeaderEntity'] if r['id']==page['headerEntityId'])
            assert (header['width'],header['height'],header['version'])==(1200,900,6)
            chunks=linked('CommandRecordEntity',owner)
            sequence=[]
            for c in chunks:
                data=z.read('lesson/'+name+'/'+c['fileName'])
                assert format(int.from_bytes(hashlib.sha256(data).digest(),'big'),'x').rjust(32,'0')==c['validate']
                sequence.extend(r['commandEnum'] for r in targets('CommandRecordEntity',c['id'],'CommandInfoEntity'))
            assert sequence==([1,1] if name=='p1' else [1,1,3])
            touch=linked('TouchRecordEntity',owner)
            texts=[r['content'] for rec in linked('TextRecordEntity',owner) for r in targets('TextRecordEntity',rec['id'],'TextInfoEntity')]
            points=sum(len(targets('TouchEventEntity',event['id'],'TouchInfoEntity')) for rec in touch for event in targets('TouchRecordEntity',rec['id'],'TouchEventEntity'))
            if name=='p1':assert points>=2 and texts==[]
            else:assert points==0 and texts==['Page two']
            results.append(dict(page=name,dimensions=[header['width'],header['height']],command_enums=sequence,
                                touch_points=points,texts=texts))
    return dict(zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                mdb_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),pages=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('database',type=Path)
    a=parser.parse_args()
    print(json.dumps(verify(a.archive,a.database),ensure_ascii=False,indent=2))
