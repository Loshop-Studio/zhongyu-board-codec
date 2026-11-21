"""Exercise the public decoder on MDB-only, mixed and legacy notebook inputs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'reports/evidence/board'


def run(path, *args, ok=True):
    result = subprocess.run([sys.executable, ROOT / 'tools/read-data.py', path, *args],
                            capture_output=True, text=True)
    if ok:
        result.check_returncode()
        return json.loads(result.stdout)
    assert result.returncode == 2 and 'Traceback' not in result.stderr, result.stderr
    return result.stderr


def main():
    entity = ('--entity', 'PageEntity')
    source = FIXTURES / 'page_mdb/new-notebook.mdb'
    expected = run(source, *entity)
    assert [r['dirName'] for r in expected['entities'][0]['rows']] == ['p1', 'p2']
    assert run(FIXTURES / 'cloud-mixed.zip', *entity)['entities'][0]['rows'][0]['dirName'] == 'p-local'
    assert run(FIXTURES / 'cloud-index/native.zip', '--type', 'cloud-note')['format'] == 'cloud-note-legacy-index'
    with TemporaryDirectory() as tmp:
        folder = Path(tmp) / '笔记'
        store = folder / 'page_mdb'
        store.mkdir(parents=True)
        (folder / 'index.json').write_text('[]')
        lock = store / 'lock.mdb'
        lock.write_bytes(b'lock')
        assert 'lock.mdb' in run(lock, ok=False)
        assert '缺少 data.mdb' in run(folder, ok=False)
        shutil.copyfile(source, store / 'data.mdb')
        assert run(store, *entity) == run(folder, *entity) == expected
        assert run(folder, '--type', 'cloud-note', *entity) == expected
        archive = Path(tmp) / '当前笔记.zip'
        with ZipFile(archive, 'w') as out:
            out.write(source, '外层/笔记/page_mdb/data.mdb')
        assert run(archive, *entity) == expected
        with ZipFile(archive, 'a') as out:
            out.write(FIXTURES / 'page_mdb/data.mdb', '另一册/page_mdb/data.mdb')
        multiple = run(archive, *entity)['stores']
        assert len(multiple) == 2
        assert next(s for s in multiple if s['member'].startswith('外层'))['database'] == expected
        assert lock.read_bytes() == b'lock' and (store / 'data.mdb').read_bytes() == source.read_bytes()
    print('Verified raw MDB, store and notebook folders, MDB-only ZIP, mixed ZIP, multi-store ZIP, legacy index and missing-data errors.')


if __name__ == '__main__':
    main()
