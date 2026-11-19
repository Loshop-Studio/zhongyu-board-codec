"""Compare two Android eraser runs with a Chromium edit and its Android readback."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from compare_sketch_render import paper_rectangle


def read_json(path):
    return json.loads(path.read_text())


def rgb(path):
    with Image.open(path) as image:
        return image.convert('RGB')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def red_mask(image):
    red, green, blue = image.split()
    return ImageChops.darker(red.point(lambda v: 255 if v == 255 else 0),
                             ImageChops.lighter(green, blue).point(lambda v: 255 if v == 0 else 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('native', 'browser', 'readback', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    runs = read_json(args.native/'native.json')
    readbacks = read_json(args.readback/'native.json')
    apps = [run['app'] for run in runs]
    assert apps == ['错题本', '新测评'] == [run['app'] for run in readbacks]
    cases = runs[0]['cases']
    assert len(cases) == 17 and runs[1]['cases'] == cases
    drag = next(case for case in cases if case['name'] == 'drag')
    initial = (args.native/'input.bin').read_bytes()
    web = (args.browser/'web.bin').read_bytes()
    assert (args.browser/'miss.bin').read_bytes() == (args.browser/'undo.bin').read_bytes() == initial
    assert (args.browser/'redo.bin').read_bytes() == web
    assert sha(web) == drag['bin_sha256']
    native_page = rgb(args.native/apps[0]/'drag.png')
    results = []
    for run in readbacks:
        app = run['app']
        [reopened] = run['cases']
        assert reopened['surviving_colors'] == drag['surviving_colors'] and reopened['bin_sha256'] == sha(web)
        assert (args.readback/app/'reopened.bin').read_bytes() == (args.native/app/'drag.bin').read_bytes() == web
        for image in (args.native/app/'drag.png', args.readback/app/'reopened.png'):
            assert ImageChops.difference(native_page, rgb(image)).getbbox() is None
        results.append(dict(app=app, apk_sha256=run['apk_sha256'], surviving_paths=len(reopened['surviving_colors']),
                            saved_bytes=len(web), readback_bitmap_matches_native_drag=True))
    browser = read_json(args.browser/'browser.json')
    held = rgb(args.browser/'held.png')
    released = rgb(args.browser/'released.png')
    paper = tuple(browser['paper'])
    assert paper_rectangle(held) == paper == paper_rectangle(released)
    mask = red_mask(held.crop(paper))
    box = mask.getbbox()
    x, y = browser['contacts'][0]
    w, h = browser['nativePage']
    sx, sy = (paper[2]-paper[0])/w, (paper[3]-paper[1])/h
    assert box and max(abs(a-b) for a,b in zip(box, ((x-40)*sx, (y-40)*sy, (x+40)*sx, (y+40)*sy))) < 2
    assert red_mask(released.crop(paper)).getbbox() is None
    editor = rgb(args.browser/'editor.png')
    projected = editor.crop(paper_rectangle(editor)).resize(native_page.size, Image.Resampling.BOX)
    def ink(image):
        return image.convert('L').point(lambda shade: 255 if shade < 180 else 0)
    a, b = ink(native_page), ink(projected)
    shared = ImageChops.darker(a,b).histogram()[255]
    union = ImageChops.lighter(a,b).histogram()[255]
    assert shared / union > .95
    report = dict(original_cases_per_app=len(cases), native_apps_match_all_cases=True,
                  input_sha256=sha(initial), web_sha256=sha(web), browser=browser, readback=results,
                  cursor=dict(held_red_pixels=mask.histogram()[255], released_red_pixels=0,
                              held_bounds_relative_to_paper=box),
                  raster=dict(size=native_page.size, threshold='luma < 180', browser_filter='BOX',
                              native_ink=a.histogram()[255], browser_ink=b.histogram()[255],
                              intersection=shared, union=union, iou=round(shared/union,6)))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    main()
