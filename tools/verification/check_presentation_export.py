"""Compare the exported file members and the visible stroke against the active slide."""
import json
from hashlib import sha256
import sys
from zipfile import ZipFile
from PIL import Image
from verify_sketch_players import BOARD

def main(native=False):
    prefix="native-presentation" if native else "presentation"
    source=BOARD/('native-sketch-presentation.zip' if native else 'sketch-presentations.zip')
    edited=BOARD/f'web-sketch-{prefix}.zip'
    with ZipFile(source) as a, ZipFile(edited) as b:
        assert set(a.namelist())==set(b.namelist())
        changed=[n for n in a.namelist() if a.read(n)!=b.read(n)]
        assert changed==[('native-presentation' if native else 'slides')+'/actions.bin']
        same=len(a.namelist())-len(changed)
    dom=json.loads((BOARD/f'{prefix}-browser.json').read_text())
    stroke=dom['stroke']
    x=(stroke['x']+stroke['endX'])/2
    y=stroke['y']
    with Image.open(BOARD/f'sketch-{prefix}-browser.png') as picture:
        img=picture.convert('RGB')
        color=img.getpixel((int(x),int(y)))
        backdrop=img.getpixel((int(x),int(y+12)))
    assert max(color)<100 and backdrop==(235,186,116),(color,backdrop)
    result=dict(sourceSha256=sha256(source.read_bytes()).hexdigest(),exportSha256=sha256(edited.read_bytes()).hexdigest(),
        changedMembers=changed,unchangedMembers=same,strokeRgb=color,adjacentSlideRgb=backdrop)
    (BOARD/f'{prefix}-export.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result)
if __name__=='__main__':main('--native' in sys.argv)
