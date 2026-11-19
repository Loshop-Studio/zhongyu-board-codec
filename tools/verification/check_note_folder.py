"""Check file-preserving directory export, changed chunks and original transfer-manifest hashes."""
from pathlib import Path
import hashlib
import json
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from note_bundle import inspect

def verify(source,folder,edited):
    with ZipFile(source) as original,ZipFile(folder) as first,ZipFile(edited) as final:
        files={x.filename for x in original.infolist() if not x.is_dir()}
        assert files==set(first.namelist()) and all(original.read(n)==first.read(n) for n in files)
        changed=sorted(n for n in files if final.read(n)!=original.read(n))
        assert changed==['p1/router.bin','p1/snapshot.bin'],changed
        new=sorted(set(final.namelist())-files)
        assert len(new)==3 and 'p1/screenshot.png' in new and any(n.endswith('_touch.bin') for n in new) and any(n.endswith('_command.bin') for n in new),new
        assert final.read('p1/screenshot.png').startswith(b'\x89PNG\r\n\x1a\n')
    result={'original_regular_files':len(files),'changed':changed,'created':new,'archives':{}}
    for label,file in [('native_zip',source),('folder_export',folder),('edited',edited)]:
        note=inspect(file)['notes'][0]
        assert note==inspect(file,'https://note.invalid/local-fixture/')['notes'][0]
        expected={'match':15,'changed':2} if label=='edited' else {'match':17}
        assert note['counts']==expected
        assert note['unlisted']==(new if label=='edited' else [])
        result['archives'][label]=dict(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),manifest=note['counts'],
                                       unlisted=note['unlisted'])
    return result

if __name__=='__main__':
    print(json.dumps(verify(*map(Path,sys.argv[1:])),ensure_ascii=False,indent=2))
