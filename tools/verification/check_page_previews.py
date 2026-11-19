"""Compare PNGs inside downloaded V6 notes to the original Android list reader and renderer."""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'reports/evidence/board'


def members(path):
    with ZipFile(path) as archive:
        return {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_pixels(a, b):
    return a.size == b.size and a.convert('RGBA').tobytes() == b.convert('RGBA').tobytes()


def footprint(a, b, region):
    def mask(image):
        return image.crop(region).convert('L').point(lambda value: 255 if value < 215 else 0)
    web, android = mask(a), mask(b)
    intersection = ImageChops.darker(web, android).histogram()[255]
    union = ImageChops.lighter(web, android).histogram()[255]
    assert union and intersection, region
    shift = max(abs(x-y) for x,y in zip(web.getbbox(), android.getbbox()))
    return dict(iou=round(intersection/union, 6), union=union, intersection=intersection,
                max_bounds_difference_px=shift)


def check_note(work, variant, source):
    base = work / variant
    browser, device = base / 'browser', base / 'returned'
    initial = members(source)
    path, = [n for n in initial if n.endswith('/screenshot.png')]
    for filename in ('untouched.zip', 'undone.zip'):
        assert (browser / filename).read_bytes() == source.read_bytes()
    archive = browser / 'web-native-v6.zip'
    edited = members(archive)
    assert edited == members(browser / 'redone.zip') == members(browser / 'web-native-v6-cloud.zip')
    assert edited[path] != initial[path]
    preview = Image.open(BytesIO(edited[path]))
    source_png = Image.open(BytesIO(initial[path]))
    normal = variant == 'normal'
    scroll = variant == 'scroll'
    if scroll:
        assert source_png.size == (1280, 837)
        assert preview.size == (1280, 907)
    else:
        assert preview.size == source_png.size == ((641, 481) if normal else (640, 480))
    assert preview.mode == source_png.mode == ('RGBA' if normal else 'RGB')
    assert preview.convert('RGBA').getpixel((0, 0)) == (255, 255, 255, 255)
    listed, native = device / 'list.png', device / ('opened.png' if normal else 'content.png')
    assert same_pixels(preview, Image.open(listed))
    native_image = Image.open(native)
    assert native_image.size == preview.size
    regions = dict(green=(0,0,310,170), red=(300,170,480,260), added=(120,255,440,420))
    if scroll:
        regions.update(red=(300,746,480,836), added=(120,831,440,907))
    strokes = {k: footprint(preview, native_image, region) for k,region in regions.items()}
    assert all(s['iou'] > .90 and s['max_bounds_difference_px'] <= 1 for s in strokes.values()), strokes
    resized = members(browser / 'web-native-v6-two-pages.zip')
    assert resized[path] == edited[path]
    blank = Image.open(BytesIO(resized['p2/screenshot.png']))
    assert blank.size == (641,481) and blank.getcolors(1) == [(641*481,(255,255,255,255))]
    return dict(source_zip_sha256=sha(source.read_bytes()), edited_zip_sha256=sha(archive.read_bytes()),
                original_png_sha256=sha(initial[path]), edited_png_sha256=sha(edited[path]),
                page_member=path, png_mode=preview.mode, source_dimensions=source_png.size, dimensions=preview.size,
                original_corner_rgba=source_png.convert('RGBA').getpixel((0,0)),
                reopened_corner_rgba=preview.convert('RGBA').getpixel((0,0)),
                original_list_decoded_identical_rgba=True,
                original_renderer_png_sha256=sha(native.read_bytes()), strokes=strokes,
                undo_original_zip_identical=True, redo_and_cloud_all_members_identical=True,
                second_page_blank=True, first_preview_preserved_on_add=True)


def check_artwork(work):
    def png(zip_path):
        return Image.open(BytesIO(members(zip_path)['lesson/p1/screenshot.png'])).convert('RGB')
    preview = png(work / 'art/web-artwork-edited.zip')
    native = Image.open(FIXTURES / 'artwork-edit-native.png')
    assert preview.size == (801,601)
    regions = dict(title=(35,30,390,107), oval=(35,135,230,253), polygon=(233,124,395,245))
    result = {k: footprint(preview, native, box) for k,box in regions.items()}
    assert result['title']['max_bounds_difference_px'] <= 2
    assert all(result[k]['iou']>.95 for k in ('oval','polygon'))
    box = (455,120,698,340)
    moved = png(work / 'image/web-page-image.zip').crop(box)
    android = Image.open(FIXTURES / 'page-image-native.png').convert('RGB').crop(box)
    native_rgb, web_rgb = android.tobytes(), moved.tobytes()
    total = moved.width*moved.height
    exact = sum(native_rgb[i:i+3] == web_rgb[i:i+3] for i in range(0,len(native_rgb),3))
    assert exact/total > .97
    result['rotated_image'] = {'exact_rgb':exact,'compared':total}
    for color in (bytes([48,118,173]), bytes([181,220,239])):
        hits = [i for i in range(0,len(native_rgb),3) if native_rgb[i:i+3] == color]
        matched = sum(web_rgb[i:i+3] == color for i in hits)
        assert len(hits)>500 and matched/len(hits)>.94
        result['rotated_image'][color.hex()] = [matched, len(hits)]
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('work', type=Path)
    work = cli.parse_args().work
    result = dict(normal=check_note(work, 'normal', FIXTURES/'native-v6-recording.zip'),
                  content=check_note(work, 'content', work/'content-original/native-v6-content.zip'),
                  scroll=check_note(work, 'scroll', work/'scroll/native-scroll.zip'),
                  artwork=check_artwork(work))
    print(json.dumps(result, ensure_ascii=False, indent=2))
