"""Compare PNG/JPEG coverage, ink occlusion and snapshot opacity after native and web rendering."""
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageChops

from compare_sketch_render import paper_rectangle

BOARD = Path(__file__).resolve().parents[2] / 'reports/evidence/board'

def compare(name):
    native = Image.open(BOARD / (name + '-native.png')).convert('RGB')
    browser = Image.open(BOARD / (name + '-web.png')).convert('RGB')
    rect = paper_rectangle(browser)
    assert abs((rect[2] - rect[0])/(rect[3] - rect[1]) - native.width/native.height) < .005
    rendered = browser.crop(rect).resize(native.size, Image.Resampling.LANCZOS)
    def coverage(im):
        channels = im.split()
        highest = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
        lowest = ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])
        return ImageChops.subtract(highest,lowest).point(lambda v: 255 if v>45 else 0)
    a, b = coverage(native), coverage(rendered)
    overlap = ImageChops.darker(a,b).histogram()[255]
    union = ImageChops.lighter(a,b).histogram()[255]
    assert union > 5000 and overlap / union > .965, (name,overlap,union,rect)
    # Check a stroke crossing above the centre tile, an earlier stroke obscured
    # by that tile, a JPEG quadrant, or the restored half-opacity image.
    if name in ('image-recording','image-v2','image-v3'):
        sites = [(104,91),(191,98),(102,149)]
    elif name in ('image-v4','image-v5'):
        sites = [(234,190),(365,194),(250,277)]
    else:
        sites = [(314,249),(300,275),(385,240),(285,46)]
    probes = []
    for xy in sites:
        n, w = native.getpixel(xy), rendered.getpixel(xy)
        assert max(abs(x-y) for x,y in zip(n,w))<=12, (name,xy,n,w)
        probes.append({'xy':xy,'native_rgb':n,'web_rgb':w})
    return dict(name=name,web_crop=rect,native_colour_pixels=a.histogram()[255],
                web_colour_pixels=b.histogram()[255],intersection=overlap,union=union,probes=probes)

def main():
    with ZipFile(BOARD/'sketch-images.zip') as src, ZipFile(BOARD/'web-sketch-images.zip') as export:
        for name in src.namelist():
            if '/res/' in name: assert src.read(name)==export.read(name)
        assert export.read('illustration/res/center-2.png')==src.read('illustration/res/center.png')
    last = json.loads((BOARD/'image-edit-frames.json').read_text())[-1]
    assert [item['image'] for item in last['layers'] if isinstance(item,dict)] == ['center.png','icons/upper.jpg','center-2.png']
    assert last['layers'].count('stroke') == 3
    names = ('illustration','image-edit','image-recording','image-v2','image-v3','image-v4','image-v5')
    rows = [compare(name) for name in names]
    for left,right in ((2,3),(4,5)):
        a=Image.open(BOARD / f'image-v{left}-native.png').convert('RGBA').tobytes()
        b=Image.open(BOARD / f'image-v{right}-native.png').convert('RGBA').tobytes()
        assert a==b
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
