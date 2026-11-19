"""A local HTML deck exercising the five calls present in each vendor WebView."""
from pathlib import Path
import subprocess,tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from sketch_image_fixture import image

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/evidence/board'
DECK='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="css/slide.css"></head><body><main><h1 id="title"></h1>
<img alt="本地课件插图" src="media/tile.png"><div id="step"></div></main><script src="js/deck.js"></script></body></html>'''
STYLE='''html,body,main{margin:0;width:100%;height:100%;overflow:hidden}main{font:24px sans-serif;background:#b3dace}
h1{margin:0;padding:12px}img{width:80px;height:50px}#step{height:36px;width:115px;background:url("../media/tile.png")}'''
SCRIPT='''let page=1,step=0;const trace=[];
function show(method) {
 trace.push(method); document.getElementById("title").textContent="Slide "+page+" / 3 · "+step;
 document.querySelector("main").style.backgroundColor=["#b3dace","#ebba74","#8cb1de"][page-1];
 document.getElementById("step").hidden=!step;
 SlideNative.setTotalCount(3); SlideNative.setCurrentSlide(page);
}
window.Presentation={
 Next(){if(step===0)step=1;else{page=Math.min(3,page+1);step=0}show("Next")},
 Prev(){if(step===1)step=0;else{page=Math.max(1,page-1);step=1}show("Prev")},
 NxtSlide(){page=Math.min(3,page+1);step=0;show("NxtSlide")},
 PrvSlide(){page=Math.max(1,page-1);step=0;show("PrvSlide")},
 GotoSlide(n){page=Math.max(1,Math.min(3,Number(n)));step=0;show("GotoSlide:"+typeof n)}
};show("load");'''
IDENTITY='matrix:[1,0,0,0,1,0,0,0,1] childExtendMatrix:[1,0,0,0,1,0,0,0,1]'
def main():
    with tempfile.TemporaryDirectory() as tmp,ZipFile(ROOT/'中育apk/错题本.apk') as apk:
        for f in ('DrawBoard.proto','SketchGraphSnapshot.proto'):
            Path(tmp,f).write_bytes(apk.read(f).removeprefix(b'\xef\xbb\xbf'))
        def encode(proto,typ,data):
            return subprocess.run(['protoc','-I'+tmp,'-I/usr/include','--encode='+typ,proto],input=data.encode(),capture_output=True,check=True).stdout
        def anymsg(typ,payload):
            wire=encode('SketchGraphSnapshot.proto' if typ=='File' else 'DrawBoard.proto',typ,payload)
            return 'type_url:"type.googleapis.com/'+typ+'" value:"'+''.join('\\%03o'%b for b in wire)+'"'
        def action(typ,kind,payload,extra=''):
            return 'ActionContent{type:'+kind+' action{'+anymsg(typ,payload)+'} '+extra+'}'
        snapshot='graphSnapshot{'+IDENTITY+' childGraph{graphType:WEB_VIEW_GRAPH name:"embedded" color:-16777216 matrix:[1,0,54,0,1,47,0,0,1] '+\
            'outRect{right:320 bottom:200} extra{'+anymsg('File','fileName:"lesson.html" width:320 height:200 viewWidth:640 viewHeight:480')+'}}}'
        request='path:"lesson.html" width:480 height:300 viewWidth:640 viewHeight:480'
        def board(ver,audio):
            items=[]
            if audio:items.append(action('AudioStartAction','ACTION_AUDIO_START','startTime:10000 fileName:"first.wav"','graphSnapshot{'+IDENTITY+'}'))
            items.append(action('ActionWebViewConfig','ACTION_WEB','startTime:10400 '+request,snapshot))
            if audio:items.append(action('AudioStopAction','ACTION_AUDIO_STOP','startTime:11200 fileName:"first.wav"','graphSnapshot{'+IDENTITY+'}'))
            return encode('DrawBoard.proto','DrawBoard',f'boardHead{{version:{ver} width:640 height:480 type:{2 if audio else 1}}} boardBody{{'+' '.join(items)+'}')
        assets={'res/ppt/lesson.html':DECK,'res/ppt/css/slide.css':STYLE,'res/ppt/js/deck.js':SCRIPT,
                'res/ppt/media/tile.png':image('PNG',('#dd4466','#443388','#ffaa33'))}
        target=Path(tmp,'fixture.zip')
        with ZipFile(target,'w') as z,ZipFile(OUT/'sketch-recording.zip') as audio:
            def add(path,data):
                z.writestr(ZipInfo(path),data,compress_type=ZIP_DEFLATED)
            for name,ver,record in [('slides',5,False),('slides-recording',5,True)]+[(f'slides-v{i}',i,False) for i in range(2,6)]:
                add(name+'/actions.bin',board(ver,record))
                for path,data in assets.items():add(name+'/'+path,data)
                if record:add(name+'/res/audio/first.wav',audio.read('recording/res/audio/first.wav'))
        (OUT/'sketch-presentations.zip').write_bytes(target.read_bytes())
if __name__=='__main__':main()
