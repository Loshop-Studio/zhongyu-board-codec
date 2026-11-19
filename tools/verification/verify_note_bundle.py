"""Compare the mistake-book APK's ZIP and JSON manifest with the offline Flutter export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
BOARD=ROOT/'reports/evidence/board'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial')
    serial=parser.parse_args().serial
    if not serial.startswith('emulator-'):parser.error('Supply an emulator serial')
    with tempfile.TemporaryDirectory(prefix='zy-note-bundle-') as temp:
        work=Path(temp)
        source=BOARD/'web-artwork-edited.zip'
        with ZipFile(source) as z:z.extractall(work)
        note=work/'lesson'
        shutil.copy(BOARD/'artwork-edit-native.png',note/'screenshot.png')
        output=work/'native-note-bundle.zip'
        env=dict(os.environ,NOTE_BUNDLE_DIR=str(note),NOTE_BUNDLE_OUTPUT=str(output))
        process=subprocess.run(['bash',ROOT/'tools/verification/verify_page.sh',serial],env=env,stdout=subprocess.PIPE)
        log=process.stdout.decode().strip()
        if process.returncode:print(log);process.check_returncode()
        with ZipFile(output) as archive:
            files={n:archive.read(n) for n in archive.namelist() if not n.endswith('/')}
            assert 'empty-folder/' in archive.namelist()
            manifest=json.loads(files.pop('fileList.json'))
            checks={row['url'].removeprefix('https://note.invalid/local-fixture/'):row['md5'] for row in manifest}
            assert len(manifest)==len(files)==len(checks) and files.keys()==checks.keys()
            for name,data in files.items():
                assert data==(note/name).read_bytes()
                assert hashlib.md5(data).hexdigest().upper()==checks[name]
        shutil.copy(output, BOARD/output.name)
        (BOARD/'native-note-bundle.json').write_text(json.dumps(dict(
            apk_sha256=hashlib.sha256((ROOT/'中育apk/错题本.apk').read_bytes()).hexdigest(),
            input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            zip_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
            native=log,entries=len(manifest),files=checks,empty_directory='empty-folder/',
        ),ensure_ascii=False,indent=2)+'\n')
        print(log)
if __name__=='__main__':main()
