"""Compare Chromium V6 seek screenshots with frames from the original Android player."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter
from compare_sketch_render import paper_rectangle, count


def compare(directory):
    browser=json.loads((directory/'browser.json').read_text())
    results=[]
    for row in browser['trace']:
        screenshot=Image.open(directory/row['png']).convert('RGB')
        native=Image.open(directory/'native'/f"frame-{row['reference']}.png").convert('RGB')
        crop=paper_rectangle(screenshot)
        assert abs((crop[2]-crop[0])/(crop[3]-crop[1])-4/3)<0.006,crop
        web=screenshot.crop(crop).resize(native.size,Image.Resampling.LANCZOS)
        def mask(image):
            # Ink has higher green than red. Text uses a neutral grey.
            return ImageChops.subtract(image.getchannel('G'),image.getchannel('R')).point(lambda d:255 if d>=20 else 0)
        a,b=mask(native),mask(web)
        na,nb=count(a),count(b)
        overlap=count(ImageChops.darker(a,b))
        near_a=count(ImageChops.darker(a,b.filter(ImageFilter.MaxFilter(3))))
        near_b=count(ImageChops.darker(b,a.filter(ImageFilter.MaxFilter(3))))
        if na==0:
            assert nb==0,(row,nb)
        else:
            assert overlap/max(na,nb)>.88 and near_a/na>.98 and near_b/nb>.98,(row,na,nb,overlap,near_a,near_b)
        results.append({'selected_ms':row['actual'],'native_reference_ms':row['reference'],
                        'browser_paper':crop,'native_ink_pixels':na,'web_ink_pixels':nb,'exact_positions':overlap,
                        'native_within_1px':near_a,'web_within_1px':near_b})
    return {'input_sha256':hashlib.sha256((Path(__file__).resolve().parents[2]/'reports/evidence/board/page-replay.zip').read_bytes()).hexdigest(),
            'browser_edit_sha256':hashlib.sha256((directory/'web-page-replay.zip').read_bytes()).hexdigest(),
            'browser_actions':{k:v for k,v in browser.items() if k!='trace'},'pixel_comparison':results}

if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('directory',type=Path)
    print(json.dumps(compare(args.parse_args().directory),indent=2))
