"""Use the original recorder to create or reopen a page, then bind its JPG to Cloud Note's sidebar."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
APP = 'local.zy.sketchthumb'
PACKAGE = 'local.zy.boardprobe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial')
    parser.add_argument('out', type=Path)
    parser.add_argument('--edited', type=Path)
    parser.add_argument('--reader', choices=('错题本','优课畅学','新测评','随身答','中育云笔记'), default='错题本')
    args = parser.parse_args()
    if not re.fullmatch(r'emulator-\d+', args.serial):
        parser.error('Use a disposable Android emulator')
    if not args.edited and args.reader != '错题本':
        parser.error('Create the common input with 错题本, then use --edited to compare readers')
    sdk = Path(os.environ.get('ANDROID_HOME', '/home/jdz/dev/android-sdk'))
    bt = sdk / 'build-tools/35.0.0'
    platform = sdk / 'platforms/android-35/android.jar'
    args.out.mkdir(parents=True, exist_ok=True)

    def call(*cmd, data=None):
        return subprocess.run(cmd, input=data, stdout=subprocess.PIPE, check=True).stdout

    def adb(*cmd, data=None):
        return call(sdk/'platform-tools/adb', '-s', args.serial, *cmd, data=data)

    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        assets = tmp/'assets'
        assets.mkdir()
        for dest, name in [('reader', args.reader), ('cloud', '中育云笔记')]:
            (assets/(dest+'.apk')).symlink_to(ROOT/'中育apk'/(name+'.apk'))
        manifest = tmp/'AndroidManifest.xml'
        manifest.write_text(f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{APP}"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/><application android:debuggable="true" android:theme="@android:style/Theme.Material.Light"><activity android:name="{PACKAGE}.PptWebViewProbe"/></application><instrumentation android:name="{PACKAGE}.SketchThumbnailProbe" android:targetPackage="{APP}"/></manifest>')
        inputs = [Path(__file__).with_name(n+'.java') for n in ('SketchThumbnailProbe','NativePlayerProbe','PptWebViewProbe')]
        call('javac','--release','8','-cp',platform,'-d',tmp,*inputs)
        call(bt/'d8','--min-api','26','--lib',platform,'--output',tmp,*sorted((tmp/'local/zy/boardprobe').glob('*.class')))
        apk = tmp/'probe.apk'
        call(bt/'aapt2','link','-I',platform,'--manifest',manifest,'-o',apk)
        with ZipFile(apk,'a') as z:
            z.write(tmp/'classes.dex','classes.dex')
            for asset in sorted(assets.iterdir()):
                z.write(asset,'assets/'+asset.name)
        call(bt/'zipalign','-f','4',apk,tmp/'aligned.apk')
        call(bt/'apksigner','sign','--ks',ROOT/'.work/build/debug.jks','--ks-pass','pass:android','--out',tmp/'signed.apk',tmp/'aligned.apk')
        adb('install','-r',tmp/'signed.apk')
    adb('shell','pm','clear',APP)
    if args.edited:
        with ZipFile(args.edited) as z:
            for member in z.infolist():
                if member.is_dir() or not member.filename.startswith('note/'):
                    continue
                name = member.filename
                if not re.fullmatch(r'note/[a-zA-Z0-9_./-]+',name) or '..' in Path(name).parts:
                    raise ValueError(name)
                adb('shell','run-as',APP,'mkdir','-p','files/'+str(Path(name).parent))
                adb('shell','-T',f"run-as {APP} sh -c 'cat > files/{name}'",data=z.read(member))
    mode = 'read' if args.edited else 'create'
    out = adb('shell','am','instrument','-w','-r','-e','mode',mode,'-e','cloudReader',str(args.reader=='中育云笔记').lower(),APP+'/'+PACKAGE+'.SketchThumbnailProbe').decode()
    if 'INSTRUMENTATION_CODE: -1' not in out:
        raise RuntimeError(out)
    report = json.loads(adb('exec-out','run-as',APP,'cat','files/report.json'))
    names = ['sidebar.png']
    if 'load_error' not in report:
        names.extend(['recorder.png', 'recorder.jpg', 'alpha.jpg'])
    else:
        assert args.reader == '中育云笔记' and 'makeExtensionsImmutable' in report['load_error']
    for name in names:
        (args.out/name).write_bytes(adb('exec-out','run-as',APP,'cat','files/'+name))
    report['reader'] = args.reader
    report['reader_sha256'] = hashlib.sha256((ROOT/'中育apk'/(args.reader+'.apk')).read_bytes()).hexdigest()
    report['sidebar_apk_sha256'] = hashlib.sha256((ROOT/'中育apk/中育云笔记.apk').read_bytes()).hexdigest()
    (args.out/'report.json').write_text(json.dumps(report, ensure_ascii=False,indent=2)+'\n')
    if not args.edited:
        names = adb('shell','run-as',APP,'find','files/note','-type','f').decode().splitlines()
        with ZipFile(args.out/'native.zip','w') as z:
            for name in sorted(names):
                z.writestr(ZipInfo(name.removeprefix('files/')),adb('exec-out','run-as',APP,'cat',name),compress_type=ZIP_DEFLATED)
    print(json.loads((args.out/'report.json').read_bytes()))

if __name__ == '__main__':
    main()
