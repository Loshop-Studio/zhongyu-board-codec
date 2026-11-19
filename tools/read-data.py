#!/usr/bin/env python3
"""Inspect local data formats and decode board records using the supplied APK schemas."""
import argparse, json, os, shutil, sqlite3, subprocess, tempfile, zipfile
import xml.etree.ElementTree as ET
from objectbox_model import Reader
from chromium_datapack import DataPack, TBS_PACKS
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
TYPES={
 'login-server':('ServerBean.proto','ServerBean'),
 'user-profile':('UserBean.proto','UserBean'),
 'sketch':('DrawBoard.proto','DrawBoard'),'sketch1':('DrawBoard.proto','DrawBoardV1'),
 'sketch-header':('SketchHeader.proto','Header'),'simple':('SimpleBoardData.proto','SimpleBoardData'),
 'header':('Header.proto','Header'),'page-header':('PageHeader.proto','PageHeader'),
 'snapshot':('GraphSnapshot.proto','PageSnapshot'),'pages':('PageRouter.proto','PageRouter'),
 'router':('RouterRecord.proto','RouterRecord'),'command':('Command.proto','CommandSource'),
 'audio-command':('Command.proto','CommandSource'),'touch':('Source.proto','TouchSource'),
 'matrix':('Source.proto','MatrixSource'),'file':('Source.proto','FileSource'),
 'text':('Source.proto','TextSource'),'geometry':('Source.proto','GeometrySource')}
LOCAL_STORE_TYPES = {
    'ota-settings': ('UpdateSetting.proto', 'UpdateSetting'),
    'preferences-pb': ('PreferenceMap.proto', 'PreferenceMap'),
    'study-settings': ('LocalStudy.proto', 'StudyPageSettings'),
    'student-info': ('LocalStudy.proto', 'LauncherStudentInfo'),
}

def is_class_file(header):
    return (len(header) >= 10 and header[:4] == bytes.fromhex('cafebabe')
            and int.from_bytes(header[6:8], 'big') >= 45
            and int.from_bytes(header[8:10], 'big') > 0)


def inspect_class_file(path, header):
    if not is_class_file(header):
        raise ValueError('expected a JVM class file header')
    local_jdk = '/home/jdz/dev/jdk-21.0.13+9'
    jdk_home = os.environ.get('JAVA_HOME')
    candidates = [Path(jdk_home, 'bin/javap')] if jdk_home else []
    if system_javap := shutil.which('javap'):
        candidates.append(Path(system_javap))
    candidates.append(Path(local_jdk, 'bin/javap'))
    javap = next((tool for tool in candidates if os.access(tool, os.X_OK)), None)
    if javap is None:
        raise ValueError('set JAVA_HOME to a JDK containing bin/javap')
    # These APKs package the class as .bin. javap accepts a path ending in .class.
    with tempfile.TemporaryDirectory() as directory:
        input_class = Path(directory, 'Input.class')
        shutil.copyfile(path, input_class)
        result = subprocess.run([str(javap), '-s', '-p', str(input_class)],
                                text=True, capture_output=True)
    if result.returncode:
        raise ValueError('javap could not decode the class file')
    return {'format': 'jvm-class', 'major': int.from_bytes(header[6:8], 'big'),
            'minor': int.from_bytes(header[4:6], 'big'),
            'declarations': result.stdout.strip().splitlines()}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('file',type=Path)
 parser.add_argument('--app',default='错题本',help='input APK basename')
 parser.add_argument('--note-base',help='URL directory of fileList.json for local --type note-bundle comparison')
 parser.add_argument('--deleted-page', action='append', help='Android page directory known to contain .page_deleted; repeat for --type cloud-note-room')
 parser.add_argument('--entity',help='select one ObjectBox entity from data.mdb')
 parser.add_argument('--resource-id',type=int,help='write this DataPack resource to stdout as stored, resolving aliases')
 parser.add_argument('--type',choices=['pdf-progress','okdownload','filedownloader','download-room','cloud-note-room','cloud-note','chromium-pak','weather-cities','art-profile','public-suffix','jvm-class','tflite','note-bundle','disk-cache','objectbox-db','json','sqlite','zip','preferences','objectbox-model',*LOCAL_STORE_TYPES,*TYPES])
 args=parser.parse_args()
 name=args.file.name
 kind=args.type
 if not kind and args.file.is_dir() and (args.file/'index.json').is_file():
    kind='cloud-note'
 if not kind or kind=='jvm-class':
    with args.file.open('rb') as f: magic=f.read(32)
 if not kind:
    if magic[4:8]==b'TFL3':kind='tflite'
    elif name in TBS_PACKS or (name.endswith('.pak') and magic[:4]==b'\x05\0\0\0'):kind='chromium-pak'
    elif is_class_file(magic):kind='jvm-class'
    elif magic[:4] in (b'pro\x00',b'prm\x00'):kind='art-profile'
    elif magic.startswith(b'SQLite format 3\x00'):kind='sqlite'
    elif magic.startswith(b'libcore.io.DiskLruCache'):kind='disk-cache'
    elif name in ('publicsuffixes.gz','PublicSuffixDatabase.list'):kind='public-suffix'
    elif zipfile.is_zipfile(args.file):kind='zip'
    elif name=='China-City-List-latest.csv':kind='weather-cities'
    elif name=='objectbox-model.bin':kind='objectbox-model'
    elif name=='data.mdb':kind='objectbox-db'
    elif name.endswith('.preferences_pb'):kind='preferences-pb'
    elif name=='updateSettings.pb':kind='ota-settings'
    elif name=='studentInfo.pb':kind='student-info'
    elif name=='settings.pb':
        if args.app=='优课畅学':kind='study-settings'
        else:parser.error('settings.pb varies by application. For a study page file use --app 优课畅学 or --type study-settings')
    elif name in ('localAnswer.bin','localCorrectResult.bin','Correct_NeedRevise.bin'):kind='json'
    elif args.file.suffix.lower()=='.xml' and magic.lstrip().startswith(b'<'):kind='preferences'
    elif magic.lstrip().startswith((b'[',b'{')):kind='json'
    else:
        kind={'snapshot.bin':'snapshot','page_router.bin':'pages','router.bin':'router','remote_draft.bin':'simple'}.get(name)
        for suffix in ('command','touch','matrix','file','text','geometry','audio'):
            if name.endswith('_'+suffix+'.bin'):kind='audio-command' if suffix=='audio' else suffix
 if not kind:parser.error('ambiguous layout; select --type (actions.bin can contain sketch or sketch1)')
 if args.entity and kind!='objectbox-db':parser.error('--entity applies to an ObjectBox database')
 if args.note_base and kind!='note-bundle':parser.error('--note-base applies to --type note-bundle')
 if args.resource_id is not None and kind!='chromium-pak':parser.error('--resource-id applies to Chromium DataPack')
 if args.deleted_page and kind!='cloud-note-room':parser.error('--deleted-page applies to --type cloud-note-room')
 if kind=='pdf-progress':
    from pdf_progress import decode
    try:
        result=decode(args.file)
        if result is None:parser.error('expected a PdfEntity table with id, currentPage and pageCount')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (OSError,sqlite3.Error) as error:parser.error(str(error))
    return
 if kind in ('download-room','okdownload','filedownloader') or (kind=='sqlite' and args.type is None):
    from download_store import decode as decode_download
    try:
        result=decode_download(args.file, None if kind=='sqlite' else kind)
        if result is not None:
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return
    except (OSError, ValueError, sqlite3.Error) as error:parser.error(str(error))
 if kind in ('cloud-note','cloud-note-room'):
    from cloud_note import decode, room
    try:
        result=room(args.file,args.deleted_page or ()) if kind=='cloud-note-room' else decode(args.file)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (sqlite3.Error,OSError,ValueError,zipfile.BadZipFile) as error:parser.error(str(error))
    return
 if kind=='chromium-pak':
    try:
        pack=DataPack(args.file.read_bytes())
        if args.resource_id is None: print(json.dumps(pack.inventory(),ensure_ascii=False,indent=2))
        else: sys.stdout.buffer.write(pack.resource(args.resource_id))
    except (OSError,ValueError) as error:parser.error(str(error))
    return
 if kind=='art-profile':
    from art_profile import decode
    try:result=decode(args.file.read_bytes())
    except (OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='public-suffix':
    from public_suffix_store import read_public_suffixes
    try:result=read_public_suffixes(args.file)
    except (EOFError,OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='jvm-class':
    try:result=inspect_class_file(args.file,magic)
    except (OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='tflite':
    from tflite_model import describe
    try:result=describe(args.file.read_bytes())
    except ValueError as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='note-bundle':
    from note_bundle import inspect
    try:result=inspect(args.file,args.note_base)
    except (OSError,ValueError,zipfile.BadZipFile) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind in LOCAL_STORE_TYPES:
    proto,message=LOCAL_STORE_TYPES[kind]
    schema_dir=ROOT/'tools/schemas'
    with args.file.open('rb') as f:
        subprocess.run(['protoc','-I'+str(schema_dir),'--decode='+message,proto],stdin=f,check=True)
    return
 if kind=='objectbox-db':
    from objectbox_store import decode
    try:result=decode(args.file,args.entity)
    except (OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='disk-cache':
    from disk_cache import decode
    try:result=decode(args.file)
    except (OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2));return
 if kind=='objectbox-model':
    print(json.dumps(Reader(args.file.read_bytes()).model(),ensure_ascii=False,indent=2));return
 if kind=='weather-cities':
    from weather_cities import read_locations
    try: rows=read_locations(args.file)
    except (OSError,ValueError) as error:parser.error(str(error))
    print(json.dumps(rows,ensure_ascii=False,indent=2));return
 if kind=='preferences':
    root=ET.parse(args.file).getroot()
    if root.tag!='map':parser.error('expected Android SharedPreferences <map>')
    rows=[]
    for item in root:
        if 'name' not in item.attrib:parser.error('preference missing key')
        tag=item.tag
        if tag=='string':value=item.text or ''
        elif tag=='set':value=[v.text or '' for v in item.findall('string')]
        elif tag in ('int','long'):value=int(item.attrib['value'])
        elif tag=='float':value=float(item.attrib['value'])
        elif tag=='boolean':value={'true':True,'false':False}[item.attrib['value']]
        else:parser.error('unknown preference element '+tag)
        rows.append({'key':item.attrib['name'],'type':tag,'value':value})
    print(json.dumps(rows,ensure_ascii=False,indent=2));return
 if kind=='json':
    print(json.dumps(json.loads(args.file.read_bytes()),ensure_ascii=False,indent=2));return
 if kind=='zip':
    with zipfile.ZipFile(args.file) as z:
        for item in z.infolist():print(item.file_size,item.filename)
    return
 if kind=='sqlite':
    with sqlite3.connect(args.file.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for row in db.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"):print(*row,sep='\t')
    return
 apps={p.stem:p for p in (ROOT/'中育apk').glob('*.apk')}
 if args.app not in apps:parser.error('unknown APK')
 schema,msg=TYPES[kind]
 with tempfile.TemporaryDirectory() as d,zipfile.ZipFile(apps[args.app]) as z:
    if schema not in z.namelist():parser.error('schema missing from this APK')
    for member in z.namelist():
        p=Path(member)
        if p.suffix!='.proto' or p.is_absolute() or '..' in p.parts:continue
        target=Path(d)/p;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(z.read(member).removeprefix(b'\xef\xbb\xbf'))
    with args.file.open('rb') as f:
        subprocess.run(['protoc','-I'+d,'--decode='+msg,schema],stdin=f,check=True)
if __name__=='__main__':main()
