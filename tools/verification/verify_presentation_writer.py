"""Save an HTML board with the original recorder and copy its ordinary files to a ZIP."""
import json
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from verify_sketch_players import ROOT, BOARD, PACKAGE

def main(serial):
    if not serial.startswith('emulator-'):raise ValueError('Expected emulator serial')
    def adb(*args,**kw):
        return subprocess.run(['adb','-s',serial,*args],check=True,capture_output=True,**kw).stdout
    apk=ROOT/'中育apk/错题本.apk'
    with apk.open('rb') as src:
        adb('shell','-T',f"run-as {PACKAGE} sh -c 'cat > files/ppt-vendor.apk'",stdin=src)
    log=adb('shell','am','instrument','-w','-e','pptWriter','true',PACKAGE+'/.ProbeRun').decode()
    assert 'INSTRUMENTATION_CODE: -1' in log,log
    directory='files/'+re.search(r'saved=(ppt-writer-[0-9]+)',log)[1]+'/'
    paths=adb('shell','run-as',PACKAGE,'find',directory,'-type','f').decode().splitlines()
    members={}
    for path in sorted(paths):
        assert path.startswith(directory)
        members[path[len(directory):]]=adb('exec-out','run-as',PACKAGE,'cat',path)
    assert len(members['actions.bin'])>0
    with ZipFile(BOARD/'sketch-presentations.zip') as fixture:
        for name in ['lesson.html','css/slide.css','js/deck.js','media/tile.png']:
            assert members['res/'+name]==fixture.read('slides/res/ppt/'+name)
    target=BOARD/'native-sketch-presentation.zip'
    with ZipFile(target,'w',ZIP_DEFLATED) as output:
        for name,data in members.items():output.writestr('native-presentation/'+name,data)
    result=dict(apk='错题本',apkSha256=sha256(apk.read_bytes()).hexdigest(),input='lesson.html',viewport=[640,480],
                result='native-sketch-presentation.zip',members={name:sha256(data).hexdigest() for name,data in members.items()})
    (ROOT/'reports/evidence/art/presentation-writer.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(list(members))
if __name__=='__main__':main(sys.argv[1])
