"""Write a legacy cloud-note index on Android and reopen both original and browser exports."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[2]
APP='local.zy.cloudindex'
PROBE='local.zy.boardprobe.CloudIndexProbe'
TITLE='课堂本'
APK=ROOT/'中育apk/中育云笔记.apk'


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('serial')
    cli.add_argument('output',type=Path)
    cli.add_argument('--edited',type=Path)
    args=cli.parse_args()
    if not args.serial.startswith('emulator-'): cli.error('Supply a disposable emulator')
    sdk=Path(os.environ.get('ANDROID_HOME','/home/jdz/dev/android-sdk'))
    bt=sdk/'build-tools/35.0.0'; platform=sdk/'platforms/android-35/android.jar'
    args.output.mkdir(exist_ok=True,parents=True)
    def call(*cmd, data=None):
        return subprocess.run(cmd,input=data,stdout=subprocess.PIPE,check=True).stdout
    def adb(*cmd, data=None):
        return call(sdk/'platform-tools/adb','-s',args.serial,*cmd,data=data)
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp);assets=work/'assets';assets.mkdir()
        (work/'AndroidManifest.xml').write_text(f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{APP}"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/><application android:debuggable="true"/><instrumentation android:name="{PROBE}" android:targetPackage="{APP}"/></manifest>')
        shutil.copyfile(APK,assets/'cloud.apk')
        for src,dst in [('art-actions.bin','one.bin'),('web-sketch.bin','two.bin')]:
            shutil.copyfile(ROOT/'reports/evidence/board'/src,assets/dst)
        shutil.copyfile(ROOT/'中育apk/错题本.apk',assets/'mistake.apk')
        if args.edited:
            with ZipFile(args.edited) as z:
                for name in z.namelist():
                    file=Path(name)
                    if file.is_absolute() or '..' in file.parts or file.parts[0]!=TITLE: raise ValueError(name)
            shutil.copyfile(args.edited,assets/'edited.zip')
        call('javac','--release','8','-cp',platform,'-d',work,Path(__file__).with_name('CloudIndexProbe.java'),Path(__file__).with_name('NativePlayerProbe.java'))
        call(bt/'d8','--min-api','26','--lib',platform,'--output',work,*sorted((work/'local/zy/boardprobe').glob('*.class')))
        call(bt/'aapt2','link','-I',platform,'--manifest',work/'AndroidManifest.xml','-A',assets,'-o',work/'probe.apk')
        with ZipFile(work/'probe.apk','a') as z:z.write(work/'classes.dex','classes.dex')
        call(bt/'zipalign','-f','4',work/'probe.apk',work/'aligned.apk')
        call(bt/'apksigner','sign','--ks',ROOT/'.work/build/debug.jks','--ks-pass','pass:android','--out',work/'signed.apk',work/'aligned.apk')
        adb('install','-r',work/'signed.apk')
        adb('shell','pm','clear',APP)
        mode='read' if args.edited else 'create'
        log=adb('shell','am','instrument','-w','-e','mode',mode,APP+'/'+PROBE).decode()
        if 'INSTRUMENTATION_CODE: -1' not in log:raise RuntimeError(log)
        report=json.loads(adb('exec-out','run-as',APP,'cat','files/report.json'))
        assert report['editor_pages']==['第2页','第一页','第2页']
        assert [Path(s).name for s in report['index']]==['第2页','missing','第一页','第2页']
        assert len(report['resources'])==3 and report['resource_ranks']==[2,3,0,2,3,1,2,2]
        assert [Path(s).parts[-3:] for s in report['representatives']]==[('第2页','page_mdb','lock.mdb'),('第一页','page_mdb','data.mdb')]
        assert [Path(s).parts[-2:] for s in report['previews']]==[('第2页','screenshot.png'),('第一页','screenshot.png')]
        assert report['marker_created'] and not report['marker_recreated'] and report['representatives_after_restore']==3
        with tarfile.open(fileobj=io.BytesIO(adb('exec-out','run-as',APP,'tar','cf','-','-C','files',TITLE))) as archive:
            members={item.name:archive.extractfile(item).read() for item in archive.getmembers() if item.isfile()}
        note=args.output/('reopened.zip' if args.edited else 'original.zip')
        with ZipFile(note,'w',compression=ZIP_DEFLATED) as z:
            for name,data in sorted(members.items()): z.writestr(ZipInfo(name),data,compress_type=ZIP_DEFLATED)
        if args.edited:
            with ZipFile(args.edited) as z:assert members=={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
        (args.output/'page-order.db').write_bytes(adb('exec-out','run-as',APP,'cat','databases/page-order.db'))
        expected_strokes=3 if args.edited else 2
        assert report['mistake_sketch']=={'第2页':f'durationMs=0 strokes={expected_strokes}','第一页':'durationMs=0 strokes=1'}
        assert report['room_live_count']==7 and report['room_representatives']==report['representatives']
        assert report['editor_with_room']==['marker-check','第2页','第一页']
        report['apk_sha256']=hashlib.sha256(APK.read_bytes()).hexdigest()
        report['members_sha256']={n:hashlib.sha256(b).hexdigest() for n,b in members.items()}
        (args.output/(mode+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('Original Android editor pages:',report['editor_pages'])
if __name__=='__main__':main()
