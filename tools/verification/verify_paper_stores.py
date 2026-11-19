"""Call the five APKs' V6 paper readers and any matching standalone writers on ART."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from check_native_page_recording import ROOT, schema_reader

WIRE='Lcom/zykj/board/EzyHeader$BackgroundLineConfig;'
ENTITY='Lcom/zykj/blackboard/core/data/dao/BackgroundLineConfigEntity;'
APPS=['错题本','优课畅学','新测评','随身答','中育云笔记']


def converter(directory,inp,out,optional=False):
    signature = '('+inp+')'+out
    pattern = r'^\.method .*? ([^\s(]+)'+re.escape(signature)+'$'
    search = subprocess.run(['rg','-l','--glob','*.smali',pattern,str(directory)],capture_output=True,text=True)
    if optional and search.returncode==1: return None
    search.check_returncode()
    files = search.stdout.splitlines()
    matches=[]
    for filename in files:
        code=Path(filename).read_text()
        owner=re.search(r'^\.class .* L([^;]+);',code,re.M)[1].replace('/','.')
        for method in re.findall(pattern,code,re.M):
            matches.append((owner,method,Path(filename)))
    if len(matches)!=1: raise ValueError(matches)
    return matches[0]


def check(serial):
    if not serial.startswith('emulator-'): raise ValueError('Supply a disposable Android emulator')
    sdk=Path(os.environ.get('ANDROID_HOME','/home/jdz/dev/android-sdk'))
    jdk=Path(os.environ.get('JAVA_HOME','/home/jdz/dev/jdk-21.0.13+9'))
    env=dict(os.environ,PATH=str(jdk/'bin')+os.pathsep+os.environ['PATH'])
    def run(*args):
        proc=subprocess.run(args,capture_output=True,env=env,timeout=90)
        if proc.returncode: raise RuntimeError((proc.stdout+proc.stderr).decode(errors='replace')[-1500:])
        return proc.stdout
    adb=[sdk/'platform-tools/adb','-s',serial]
    platform=sdk/'platforms/android-35/android.jar'
    results=[]
    with tempfile.TemporaryDirectory(prefix='zy-paper-') as name:
        tmp=Path(name)
        run(jdk/'bin/javac','--release','8','-cp',platform,'-d',tmp,ROOT/'tools/verification/PaperStoreProbe.java')
        run(sdk/'build-tools/35.0.0/d8','--min-api','26','--lib',platform,'--output',tmp/'probe.jar',tmp/'PaperStoreProbe.class')
        remote='/data/local/tmp/zy-paper-'+uuid.uuid4().hex[:16]
        run(*adb,'shell','mkdir',remote)
        try:
            run(*adb,'push',tmp/'probe.jar',remote+'/probe.jar')
            for app in APPS:
                apk=ROOT/'中育apk'/(app+'.apk')
                load=converter(ROOT/'android'/app,WIRE,ENTITY)
                save=converter(ROOT/'android'/app,ENTITY,WIRE,optional=True)
                # The input explicitly sets a nondefault width. Use the
                # embedded schema to decode the bytes before and after ART.
                parse=schema_reader(apk)
                msg=parse('BackgroundLineConfig',b'')
                msg.lineColor=0x78443322;msg.lineSpace=37.5;msg.lineType=1;msg.lineWidth=7.5
                input_bytes=msg.SerializeToString()
                run(*adb,'push',apk,remote+'/source.apk')
                raw=run(*adb,'shell','env','CLASSPATH='+remote+'/probe.jar:'+remote+'/source.apk',
                        'app_process','/system/bin','PaperStoreProbe',*load[:2],*(save[:2] if save else ('-','-')),
                        base64.b64encode(input_bytes).decode())
                row=json.loads(next(s for s in raw.decode().splitlines() if s.startswith('{')))
                assert row['floats']==[3.0,37.5]
                assert row['line_color']==msg.lineColor and row['line_type']==msg.lineType
                returned=None
                if save:
                    returned=base64.b64decode(row['serialized'])
                    output=parse('BackgroundLineConfig',returned)
                    msg.ClearField('lineWidth')
                    assert output==msg
                results.append(dict(app=app,apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
                                    read_method='.'.join(load[:2]),write_method='.'.join(save[:2]) if save else None,
                                    input_hex=input_bytes.hex(),entity_floats=row['floats'],entity_line_color=row['line_color'],
                                    entity_line_type=row['line_type'],saved_hex=returned.hex() if save else None))
        finally:
            run(*adb,'shell','rm','-r',remote)
    return dict(android=run(*adb,'shell','getprop','ro.build.version.release').decode().strip(),apps=results)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('serial')
    print(json.dumps(check(cli.parse_args().serial),indent=2,ensure_ascii=False))
