"""Compare the original Sketch graph renderer and the Chromium Flutter canvas."""
from pathlib import Path
import json
from PIL import Image, ImageChops, ImageFilter

BOARD=Path(__file__).resolve().parents[2]/"reports/evidence/board"

def paper_rectangle(im):
    # Reset zoom and centre the board. Its outside margins use the light-grey workspace colour.
    intervals=[]
    for y in range(im.height):
        if im.getpixel((0,y)) != (231,238,236):
            continue
        xs=[x for x in range(im.width) if im.getpixel((x,y))==(255,255,255)]
        if not xs:
            continue
        edges=(xs[0],xs[-1]+1)
        if intervals and intervals[-1][:2]==edges and intervals[-1][3]==y:
            intervals[-1]=(edges[0],edges[1],intervals[-1][2],y+1)
        else:
            intervals.append((*edges,y,y+1))
    x,r,y,b=max(intervals,key=lambda row:row[3]-row[2])
    # An image at one canvas edge can hide that entire white margin for some
    # rows. Follow adjacent rows while the opposite paper edge remains visible.
    def on_paper(row):
        return row[0]>=x and row[1]<=r and (row[0]==x or row[1]==r)
    for row in reversed(intervals):
        if row[3]==y and on_paper(row): y=row[2]
    for row in intervals:
        if row[2]==b and on_paper(row): b=row[3]
    return x,y,r,b

def count(im):
    return im.histogram()[255]

def main():
    native=Image.open(BOARD/"transform-edit-native.png").convert("RGB")
    browser=Image.open(BOARD/"web-transform.png").convert("RGB")
    rect=paper_rectangle(browser)
    assert abs((rect[2]-rect[0])/(rect[3]-rect[1])-native.width/native.height)<0.005
    scaled=browser.crop(rect).resize(native.size,Image.Resampling.LANCZOS)
    def mask(image):return image.convert("L").point(lambda grey:255 if grey<130 else 0)
    a,b=mask(native),mask(scaled)
    shared=count(ImageChops.darker(a,b))
    a_near=count(ImageChops.darker(a,b.filter(ImageFilter.MaxFilter(3))))
    b_near=count(ImageChops.darker(b,a.filter(ImageFilter.MaxFilter(3))))
    result={"native_size":native.size,"browser_crop":rect,"native_dark":count(a),"web_dark":count(b),
            "same_pixel":shared,"native_near_web_1px":a_near,"web_near_native_1px":b_near}
    print(json.dumps(result,indent=2))
    assert min(count(a),count(b))>1000 and shared/max(count(a),count(b))>0.90
    assert min(a_near/count(a),b_near/count(b))>0.99

if __name__=="__main__":main()
