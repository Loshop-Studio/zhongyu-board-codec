"""Create an annotated-time V6 notebook using the protobuf schemas from the supplied APK."""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import subprocess
from page_audio_fixture import ROOT, BOARD


def build(destination):
    with TemporaryDirectory() as temp, ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for name in apk.namelist():
            if name.endswith('.proto') and ('/' not in name or name.startswith(('utils/','enums/'))):
                apk.extract(name,temp)

        def encode(schema, msg, content):
            return subprocess.run(['protoc','-I'+temp,'-I/usr/include','--encode='+msg,schema+'.proto'],
                                  input=content.encode(),capture_output=True,check=True).stdout

        with ZipFile(BOARD/'page-audio.zip') as base:
            files={n:base.read(n) for n in base.namelist() if not n.startswith('lesson/p1/') or n.endswith('_audio.bin')}
        refs=[]
        def record(name, field, raw):
            files['lesson/p1/'+name]=raw
            digest=hashlib.sha256(raw).hexdigest().lstrip('0').zfill(32)
            refs.append(f'{field} {{ fileName:"{name}" validate:"{digest}" }}')
        record('0001_audio.bin','audioRecord',files['lesson/p1/0001_audio.bin'])
        identity='scaleX:1 scaleY:1 perSp2:1'
        def matrix(x,y):return identity+f' transX:{x} transY:{y}'
        pen='color:-14664588 width:9 style:1'
        touch=' '.join(f'touchEvent {{eventTime:{t} action:{a} x:{x} y:{y} pointerCount:1 pointerCoords {{x:{x} y:{y}}}}}'
                       for t,a,x,y in [(31000,0,100,100),(31200,2,200,100),(31500,2,240,210),(31800,1,340,180)])
        record('001_touch.bin','touchSourceRecord',encode('Source','TouchSource',f'touchInfo {{paint {{{pen}}} {touch}}}'))
        record('001_matrix.bin','matrixSourceRecord',encode('Source','MatrixSource','matrixInfo {'+
               ' '.join(f'matrix {{eventTime:{t} {matrix(x,y)}}}' for t,x,y in [(7000,0,0),(7200,40,20),(7400,80,40)])+'}'))
        label='color:-13948117 textSize:28 style:0'
        record('001_text.bin','textSourceRecord',encode('Source','TextSource',f'textInfo {{content:"Before" paint {{{label}}}}}'))
        hdr='version:6 width:640 height:480 defaultBackgroundColor:-1 lastBackgroundColor:-1 duration:3100'
        files['lesson/header.bin']=files['lesson/p1/header.bin']=encode('Header','Header',hdr)
        root_rect='left:0 top:0 right:640 bottom:480'
        ink_rect='left:100 top:100 right:340 bottom:210'
        text_rect='left:75 top:260 right:330 bottom:305'
        root=f'id:"root" outRect {{{root_rect}}} matrix {{{identity}}}'
        def graph(text,delta):
            return (root+' childGraph {id:"ink" graphEnum:STROKE_GRAPH sourceFileName:"001_touch.bin" '
                    f'outRect {{{ink_rect}}} matrix {{{matrix(*delta)}}}}} '
                    f'childGraph {{id:"title" graphEnum:TEXT_GRAPH outRect {{{text_rect}}} matrix {{{identity}}} '
                    f'sourceFileName:"001_text.bin" content:"{text}" paint {{{label}}}}}')
        files['lesson/p1/snapshot.bin']=encode('GraphSnapshot','PageSnapshot',
            'cameraMatrix {'+identity+'} graphSnapshot {'+graph('After',(80,40))+' backgroundColor:-1}')
        def command(enum, kind, body, delay=0, duration=0, play=True):
            raw=encode('Command','CommandSource.CommandInfo.'+kind,body)
            literal=''.join('\\%03o'%b for b in raw)
            return f'commandInfo {{ isPlay:{str(play).lower()} delayTime:{delay} duration:{duration} commandEnum:ACTION_{enum} data:"{literal}" }}'
        shard1=[
            command('GRAPH_ADD','GraphData',f'graphId:"root" outRect {{{root_rect}}}'),
            command('GRAPH_ADD','GraphData',f'graphId:"ink" parentGraphId:"root" graphEnum:STROKE_GRAPH sourceFileName:"001_touch.bin" outRect {{{ink_rect}}}',200,800),
            command('GRAPH_REMOVE','GraphRemove','graphData {graphId:"ink" parentGraphId:"root" graphEnum:STROKE_GRAPH}',300)]
        shard2=[
            command('REBUILD','REBUILD','snapshot {'+graph('Before',(0,0))+'} backgroundColor:-1',500),
            command('GRAPH_CHANGE','GraphChange','graphId:"title" graphEnum:TEXT_GRAPH content:"After"',100,450,False),
            command('GRAPH_MATRIX','GraphMatrix','graphData {graphId:"ink" graphEnum:STROKE_GRAPH} sourceFileName:"001_matrix.bin"',400,400),
            command('CONFIG','Config','lastBackground:-1',200)]
        for i, commands in enumerate((shard1,shard2),1):
            record(f'00{i}_command.bin','commandRecord',encode('Command','CommandSource',' '.join(commands)))
        files['lesson/p1/router.bin']=encode('RouterRecord','RouterRecord',' '.join(refs))
        with ZipFile(destination,'w',ZIP_DEFLATED) as out:
            for n,d in files.items():out.writestr(ZipInfo(n),d,compress_type=ZIP_DEFLATED)


if __name__=='__main__':build(BOARD/'page-replay.zip')
