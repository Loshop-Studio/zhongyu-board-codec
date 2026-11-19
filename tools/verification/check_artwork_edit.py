"""Compare browser v6 artwork command payloads with the rows saved by the APK's JNI importer."""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / 'reports/evidence/board'
sys.path.insert(0, str(ROOT / 'tools'))
from objectbox_store import decode

def check(database, creation=False, image=False):
    stem = 'web-page-image' if image else "web-artwork-created" if creation else "web-artwork-edited"
    with tempfile.TemporaryDirectory() as tmp, ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for name in apk.namelist():
            if name.endswith('.proto') and ('/' not in name or name.startswith(('utils/', 'enums/'))):
                apk.extract(name, tmp)
        def message(kind,file,data):
            result = subprocess.run(['protoc','-I'+tmp,'-I/usr/include','--decode='+kind,file],
                                    input=data, capture_output=True, check=True)
            return result.stdout.decode()
        payloads, hashes, matrices = [], {}, []
        with ZipFile(BOARD/(stem+'.zip')) as normal, ZipFile(BOARD/(stem+'-cloud.zip')) as portable, ZipFile(BOARD/'artwork-edit-base.zip') as base:
            for path in base.namelist():
                if path.endswith(('_geometry.bin','_text.bin','_file.bin','.png')):
                    assert base.read(path) == normal.read(path) == portable.read(path)
                    hashes[path] = hashlib.sha256(base.read(path)).hexdigest()
            for path in normal.namelist():
                if path != 'lesson/p1/header.bin':
                    assert normal.read(path) == portable.read(path)
            router = message('RouterRecord','RouterRecord.proto',portable.read('lesson/p1/router.bin'))
            refs = re.findall(r'commandRecord \{\s+fileName: "(.*?)"\s+validate: "(.*?)"\s+}',router)
            assert len(refs) == (2 if image else 5 if creation else 4)
            for name,digest in refs:
                raw = portable.read('lesson/p1/'+name)
                assert format(int.from_bytes(hashlib.sha256(raw).digest(),'big'),'x').rjust(32,'0') == digest
                record = message('CommandSource','Command.proto',raw)
                payloads.extend(ast.literal_eval('b'+s) for s in re.findall(r'^  data: (".*")$',record,re.M))
            if image:
                for name, digest in re.findall(r'matrixSourceRecord \{\s+fileName: "(.*?)"\s+validate: "(.*?)"\s+}',router):
                    raw = portable.read('lesson/p1/'+name)
                    assert format(int.from_bytes(hashlib.sha256(raw).digest(),'big'),'x').rjust(32,'0') == digest
                    fields = message('MatrixSource','Source.proto',raw)
                    matrices.append(dict((k,float(v)) for k,v in re.findall(r'^    (\w+): ([^\n]+)$',fields,re.M)))
    db = decode(database)
    rows = {e['name']:e['rows'] for e in db['entities']}
    commands = rows['CommandInfoEntity']
    assert [c['commandEnum'] for c in commands] == ([3,3] if image else [1,3]*5 if creation else [4,3,4,12,3,1])
    assert [bytes.fromhex(c['data']['hex']) for c in commands] == payloads
    report = dict(input=hashlib.sha256((BOARD/(stem+'-cloud.zip')).read_bytes()).hexdigest(),
                database=hashlib.sha256(database.read_bytes()).hexdigest(),original_resources=hashes,
                entity_rows={k:len(v) for k,v in rows.items() if v},
                command_enums=[c['commandEnum'] for c in commands],
                matched_payload_sha256=[hashlib.sha256(x).hexdigest() for x in payloads])
    if image:
        fields = ('scaleX','skewX','transX','skewY','scaleY','transY','perSp0','perSp1','perSp2')
        native = [{k:row[k] for k in fields} for row in rows['MatrixInfoEntity']]
        assert len(matrices) == len(native) == 2 and all(m for m in matrices)
        import struct
        for stored, wire in zip(native,matrices):
            assert all(struct.pack('<f',stored[k]) == struct.pack('<f',wire.get(k,0)) for k in fields)
        report['native_matrix_values'] = native
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--create',action='store_true')
    modes.add_argument('--image',action='store_true')
    args=parser.parse_args()
    print(json.dumps(check(args.database, args.create, args.image),ensure_ascii=False,indent=2))
