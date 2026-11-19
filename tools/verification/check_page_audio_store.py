"""Check V6 audio page membership, stored command payloads and the original writer's output."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from objectbox_store import decode


def check(path, portable, rewritten):
    entities = {e['name']:e for e in decode(path)['entities']}
    rows = lambda name: entities[name]['rows']
    pages = rows('PageEntity')
    assert [p['dirName'] for p in pages]==['p1','p2']
    heads = {h['id']:h['duration'] for h in rows('HeaderEntity')}
    durations = [heads[p['headerEntityId']] for p in pages]
    assert durations == [4100,0]
    shard, = rows('AudioRecordEntity')
    assert shard['recordId']==pages[0]['recordEntityId'] and shard['recordId']!=pages[1]['recordEntityId']
    commands = rows('AudioInfoEntity')
    assert [(r['delayTime'],r['duration'],r['isPlay'],r['commandEnum']) for r in commands] == [
        (200,1200,True,6),(400,800,False,6),(300,1200,True,6)]
    assert entities['AudioRecordEntity']['relations'][0]['pairs']==[[shard['id'],r['id']] for r in commands]
    media = {}
    with ZipFile(portable) as archive:
        data = archive.read('lesson/p1/'+shard['fileName'])
        for row,name in zip(commands, ('first.wav','second.wav','first-2.wav')):
            # Compare wire data from the embedded DAO with the AudioStart filename and duration.
            value = bytes.fromhex(row['data']['hex'])
            name_wire = name.encode()
            duration = row['duration']
            assert value == bytes([10,len(name_wire)])+name_wire+bytes([16,128+(duration%128),duration//128])
            media[name] = hashlib.sha256(archive.read('lesson/res/audio/'+name)).hexdigest()
    digest = hashlib.sha256(data).hexdigest()
    assert data == rewritten.read_bytes()
    assert shard['validate']==digest.lstrip('0').zfill(32)
    return {'zip_sha256':hashlib.sha256(portable.read_bytes()).hexdigest(),
            'objectbox_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'page_durations_ms':durations,'audio_record_id':shard['id'],
            'page_ids':[p['id'] for p in pages], 'audio_info_rows':commands, 'media_sha256':media,
            'native_rewrite_equals_web_shard':True, 'shard_sha256':digest}


if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    for arg in ['database','portable','rewritten']: args.add_argument(arg,type=Path)
    options=args.parse_args()
    print(json.dumps(check(options.database,options.portable,options.rewritten),ensure_ascii=False,indent=2))
