from pathlib import Path
import io, math, struct, wave, zipfile, subprocess
import argparse, tempfile
args=argparse.ArgumentParser(description="Create a two-clip local recording with native Sketch schemas.")
args.add_argument("output",type=Path)
dest=args.parse_args().output
apk=Path(__file__).resolve().parents[2]/"中育apk/错题本.apk"
temp=tempfile.TemporaryDirectory()
schemas=Path(temp.name)
with zipfile.ZipFile(apk) as source:
 for name in ('DrawBoard.proto','SketchGraphSnapshot.proto'):
  (schemas/name).write_bytes(source.read(name).removeprefix(b'\xef\xbb\xbf'))
def enc(name,body):
 result=subprocess.run(['protoc','-I'+str(schemas),'-I/usr/include','--encode='+name,'DrawBoard.proto'],input=body.encode(),capture_output=True,check=True)
 return result.stdout
def literal(b):return '"'+''.join('\\%03o'%n for n in b)+'"'
head='boardHead {version:5 width:640 height:480 type:2}'
events=[]
def append(name,enum,body,snapshot=""):
 raw=enc(name,body)
 events.append('ActionContent {type:'+enum+' action {type_url:"type.googleapis.com/'+name+'" value:'+literal(raw)+'} '+snapshot+'}')
def touch(times,points):
 content=''
 for i,(t,(x,y)) in enumerate(zip(times,points)):
  action=0 if i==0 else 1 if i==len(times)-1 else 2
  content+=f'touchEvent {{eventTime:{t} action:{action} pointerCount:1 x:{x} y:{y} pointerProperties {{toolType:2}} pointerCoords {{x:{x} y:{y}}}}}'
 append('ActionTouchEvent','ACTION_TOUCH',f'startTime:{times[0]} endTime:{times[-1]} '+content)
append('ActionModeConfig','ACTION_MODE','startTime:2000 mode:ACTION_WRITING')
append('ActionGraphConfig','ACTION_GRAPH','startTime:3000 config {color:-14254549 width:6}')
empty_root='graphSnapshot{matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]}'
append('AudioStartAction','ACTION_AUDIO_START','startTime:10000 fileName:"first.wav"',empty_root)
touch([10050,10350,10700],[(45,45),(130,100),(240,50)])
append('ActionClearBoard','ACTION_CLEAR_BOARD','startTime:10900')
graph='matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]'
points=enc('Touch','pointF{x:45 y:45} pointF{x:130 y:100} pointF{x:240 y:50}')
snap='graphSnapshot {graphType:UNBOUNDED_CONTAINER_GRAPH '+graph+' childGraph {graphType:STROKE_GRAPH '+graph.replace('matrix:[1,0,0','matrix:[1,0,15')+' color:-14254549 width:6 extra {type_url:"type.googleapis.com/Touch" value:'+literal(points)+'}}}'
append('ActionPrevAction','ACTION_PREV','startTime:10950',snap)
append('AudioStopAction','ACTION_AUDIO_STOP','startTime:11200 fileName:"first.wav"')
append('ActionGraphConfig','ACTION_GRAPH','startTime:18000 config {color:-12537914 width:5}')
append('AudioStartAction','ACTION_AUDIO_START','startTime:20000 fileName:"second.wav"',empty_root)
touch([20200,20600,20750],[(300,190),(400,310),(510,190)])
final_points=enc('Touch','pointF{x:300 y:190} pointF{x:400 y:310} pointF{x:510 y:190}')
final_snapshot='graphSnapshot {graphType:UNBOUNDED_CONTAINER_GRAPH '+graph+' childGraph {graphType:STROKE_GRAPH '+graph+' color:-12537914 width:5 extra {type_url:"type.googleapis.com/Touch" value:'+literal(final_points)+'}}}'
append('AudioStopAction','ACTION_AUDIO_STOP','startTime:20800 fileName:"second.wav"',final_snapshot)
data=enc('DrawBoard',head+' boardBody {'+' '.join(events)+'}')
def tone(duration,hz):
 b=io.BytesIO()
 with wave.open(b,'wb') as w:
  w.setparams((1,2,16000,0,'NONE','not compressed'))
  w.writeframes(b''.join(struct.pack('<h',int(1200*math.sin(2*math.pi*hz*i/16000))) for i in range(duration*16)))
 return b.getvalue()
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('recording/actions.bin',data)
 z.writestr('recording/res/audio/first.wav',tone(1200,330))
 z.writestr('recording/res/audio/second.wav',tone(800,440))
