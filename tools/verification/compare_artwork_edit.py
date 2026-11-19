"""Compare original Android v6 graph rendering and a Chromium screenshot."""
import argparse
import json
from pathlib import Path
from PIL import Image
from compare_sketch_render import paper_rectangle

board = Path(__file__).resolve().parents[2]/'reports/evidence/board'
parser=argparse.ArgumentParser(description=__doc__)
modes=parser.add_mutually_exclusive_group()
modes.add_argument('--create',action='store_true')
modes.add_argument('--image',action='store_true')
args=parser.parse_args()
create=args.create
stem='page-image' if args.image else 'artwork-create' if create else 'artwork-edit'
browser = Image.open(board/(stem+'-web.png')).convert('RGB')
native = Image.open(board/(stem+'-native.png')).convert('RGB')
crop = paper_rectangle(browser)
# The image probe uses an unfiltered bitmap with two exact tile colours. Sample
# the nearest displayed pixel for this comparison, without inventing boundary colours.
sampler = Image.Resampling.NEAREST if args.image else Image.Resampling.LANCZOS
web = browser.crop(crop).resize(native.size, sampler)
assert native.size == (800,600) and abs((crop[2]-crop[0])/(crop[3]-crop[1])-4/3) < .005
regions = {'title':(35,30,390,107),'oval':(35,135,230,253),'triangle':(233,124,395,245)}
if create:
    regions={'title':(35,280,224,356),'oval':(60,380,163,465),'rectangle':(228,373,348,468),
             'triangle':(395,366,520,473),'image':(583,348,700,470)}
if args.image:
    regions={'dragged_image':(455,120,698,340)}
def coverage(image, box):
    im = image.crop(box)
    return {(x+box[0],y+box[1]) for y in range(im.height) for x in range(im.width) if min(im.getpixel((x,y))) < 190}
def bounds(points):
    xs,ys=zip(*points)
    return [min(xs),min(ys),max(xs)+1,max(ys)+1]
report = {'web_paper_crop':crop,'native_canvas':native.size,'regions':{}}
for name,region in regions.items():
    a,b=coverage(native,region),coverage(web,region)
    iou=len(a&b)/len(a|b)
    assert len(a)>100 and len(b)>100
    if name == 'title':
        # Android draws glyph paths; Chromium rasterizes the shaped text.
        assert max(abs(x-y) for x,y in zip(bounds(a),bounds(b))) <= 2
    else:
        assert iou > (.90 if create else .95), (name,iou)
    report['regions'][name]=dict(native_bounds=bounds(a),web_bounds=bounds(b),native_pixels=len(a),web_pixels=len(b),iou=round(iou,6))
if args.image:
    report['web_to_canvas_resampling'] = 'nearest'
    region = regions['dragged_image']
    report['exact_rgb_pixels'] = sum(native.getpixel((x,y))==web.getpixel((x,y))
                                     for x in range(region[0],region[2]) for y in range(region[1],region[3]))
    report['compared_rgb_pixels'] = (region[2]-region[0])*(region[3]-region[1])
    # Both tile colours count as covered. Compare each original colour as well,
    # so a wrong orientation cannot pass through a matching outer rectangle.
    tile_colours = [(48,118,173),(181,220,239)]
    for colour in tile_colours:
        hits = [px for px in a if native.getpixel(px)==colour]
        same = sum(max(abs(c-d) for c,d in zip(web.getpixel(px),colour))<=8 for px in hits)
        assert len(hits)>500 and same/len(hits)>.94
        report.setdefault('original_tile_colours',[]).append(dict(rgb=colour,native_samples=len(hits),
                       web_within_8_per_channel=same,agreement=round(same/len(hits),6)))
print(json.dumps(report,indent=2))
