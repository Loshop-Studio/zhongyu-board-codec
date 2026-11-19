"""Inspect local MediaPlayer seeks in the five original APKs on a disposable Android emulator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from page_audio_fixture import ROOT, BOARD

APPS = ['错题本', '优课畅学', '新测评', '随身答', '中育云笔记']


def check(serial, edited, output):
    sdk = Path(os.environ.get('ANDROID_HOME', '/home/jdz/dev/android-sdk'))
    java = Path(os.environ.get('JAVA_HOME', '/home/jdz/dev/jdk-21.0.13+9'))/'bin'
    env = dict(os.environ, PATH=str(java)+os.pathsep+os.environ['PATH'])
    platform = sdk/'platforms/android-35/android.jar'
    adb = [str(sdk/'platform-tools/adb'), '-s', serial]

    def run(*args):
        result = subprocess.run(args, env=env, capture_output=True, timeout=55)
        if result.returncode:
            raise RuntimeError((result.stdout+result.stderr).decode())
        return result.stdout.decode()

    cases = {'base': [(0,-1,-1),(450,1200,250),(1400,-1,-1),(1550,-1,-1),(2125,800,325),(2600,-1,-1),(2780,-1,-1)],
             'split': [(450,1200,250),(2125,-1,-1)]}
    if edited:
        cases['edited'] = [(450,1200,250),(2125,800,325),(2820,-1,-1),(3150,1200,250),(4100,-1,-1)]
        cases['other'] = [(450,-1,-1),(3150,-1,-1)]
    with tempfile.TemporaryDirectory(prefix='zy-page-audio-') as temp:
        work = Path(temp)
        bt = sdk/'build-tools/35.0.0'
        package = 'local.zy.pageaudio'
        run(java/'javac','--release','8','-Xlint:-options','-cp',platform,'-d',work,
            Path(__file__).with_name('PageAudioProbe.java'))
        (work/'dex').mkdir()
        run(bt/'d8','--min-api','26','--lib',platform,'--output',work/'dex',
            work/'local/zy/pageaudio/PageAudioProbe.class')
        (work/'AndroidManifest.xml').write_text(f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}">'
            '<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/>'
            '<application android:label="Local page audio test" android:debuggable="true"/>'
            f'<instrumentation android:name=".PageAudioProbe" android:targetPackage="{package}"/></manifest>')
        run(bt/'aapt2','link','-I',platform,'--manifest',work/'AndroidManifest.xml','-o',work/'app.apk')
        with ZipFile(work/'app.apk','a',ZIP_DEFLATED) as bundle: bundle.write(work/'dex/classes.dex','classes.dex')
        run(bt/'zipalign','-f','4',work/'app.apk',work/'aligned.apk')
        run(bt/'apksigner','sign','--ks',ROOT/'.work/build/debug.jks','--ks-pass','pass:android','--out',work/'signed.apk',work/'aligned.apk')
        run(*adb,'install','-r',work/'signed.apk')

        def put(relative, data):
            path='files/'+relative
            run(*adb,'shell','run-as',package,'mkdir','-p',str(Path(path).parent))
            subprocess.run([*adb,'shell','-T','run-as',package,'tee',path],input=data,
                           stdout=subprocess.DEVNULL,check=True,timeout=55)
        inputs = {'base':BOARD/'page-audio.zip','split':BOARD/'page-audio-split.zip'}
        if edited: inputs['edited'] = edited
        report = {'input_sha256':{name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in inputs.items()},
                  'android':run(*adb,'shell','getprop','ro.build.version.release').strip(), 'apps':[]}
        for name, path in inputs.items():
            with ZipFile(path) as archive:
                for item in archive.namelist(): put(name+'/'+item,archive.read(item))
        for app in APPS:
            apk = ROOT/'中育apk'/(app+'.apk')
            put('target.apk',apk.read_bytes())
            results = {}
            for case, expected in cases.items():
                page = 'edited/lesson/p2' if case=='other' else case+'/lesson/p1'
                log = run(*adb,'shell','am','instrument','-w','-e','page',page,'-e','times',
                          ','.join(str(i) for i,_,_ in expected),*(['-e','forward','yes'] if case=='split' else []),package+'/.PageAudioProbe')
                assert 'INSTRUMENTATION_CODE: -1' in log, log
                if case == 'split':
                    assert 'INSTRUMENTATION_RESULT: forward=240,1200|1904,800|' in log, log
                    results['split_forward_page_ms_media_duration_ms'] = [[240,1200],[1904,800]]
                values = next(line.split('=',1)[1] for line in log.splitlines() if line.startswith('INSTRUMENTATION_RESULT: seeks='))
                rows = [list(map(int, item.split(','))) for item in values.split('|') if item]
                assert len(rows)==len(expected),(app,case,log)
                for (t,d,p),(et,ed,ep) in zip(rows,expected):
                    assert t==et and d==ed and (abs(p-ep)<=35 if d>0 else p==-1),(app,case,rows,expected)
                results[case]=rows
            report['apps'].append({'app':app,'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),
                                   'seek_page_ms_media_duration_ms_media_position_ms':results})
            print(app, results, flush=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial')
    parser.add_argument('--edited',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    options=parser.parse_args()
    if not options.serial.startswith('emulator-'): parser.error('Supply an emulator serial')
    check(options.serial,options.edited,options.output)
