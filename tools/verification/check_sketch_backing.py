"""Compare two JPEG-backed note variants through edit, native reopen, and a second edit."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image

from check_sketch_thumbnail import members, pixels
from compare_sketch_render import paper_rectangle
from check_native_page_recording import schema_reader


def masks(rgb):
    red, green, blue = rgb.transpose(2, 0, 1)
    y = np.arange(red.shape[0])[:, None]
    return {
        'original_ink': (y >= 90) & (y < 205) & (red > green + 25) & (red > blue + 18) & (green < 155),
        'original_image': (y > 203) & (y < 285) & (rgb.max(2) - rgb.min(2) > 48),
        'first_edit': (y > 335) & (rgb.max(2) < 166),
        'second_edit': (y < 90) & (rgb.max(2) < 166),
    }


def compare(a, b, present):
    result = {}
    for name, left in masks(a).items():
        right = masks(b)[name]
        if name not in present:
            assert not left.any() and not right.any(), name
            continue
        union = int((left | right).sum())
        shared = int((left & right).sum())
        y, x = np.where(right)
        assert union > 250 and shared / union > .91, (name, shared, union)
        result[name] = {'shared': shared, 'union': union, 'iou': shared / union,
                        'bounds': [int(x.min()), int(y.min()), int(x.max()), int(y.max())]}
    return result


def screen(path):
    im = Image.open(path).convert('RGB')
    return pixels(im.crop(paper_rectangle(im)).resize((640, 480), Image.Resampling.LANCZOS))


def verify(original, work):
    result = []
    parse = schema_reader(Path(__file__).resolve().parents[2]/'中育apk/错题本.apk', ('DrawBoard.proto',))
    for version in (1, 5):
        browser = work/f'backing-browser/v{version}'
        readers = work/f'backing-read/v{version}'
        origin = original/f'backing-v{version}.zip'
        src, edited, twice = [members(p) for p in (origin, browser/'web.zip', browser/'again.zip')]
        expected = {'note/actions.bin', 'note/thumbnail.jpg'}
        assert src.keys() == edited.keys() == twice.keys()
        assert {k for k in src if src[k] != edited[k]} == expected
        assert {k for k in src if edited[k] != twice[k]} == expected
        message = 'DrawBoardV1' if version == 1 else 'DrawBoard'
        boards = [parse(message, package['note/actions.bin']) for package in (src, edited, twice)]
        assert boards[0].boardHead == boards[1].boardHead == boards[2].boardHead
        actions = [list((b.boardBodyV1 if version == 1 else b.boardBody).ActionContent) for b in boards]
        for earlier, later in zip(actions, actions[1:]):
            assert earlier == later[:len(earlier)]
            tail = [a if version == 1 else a.action for a in later[len(earlier):]]
            assert [a.type_url.rsplit('/',1)[-1] for a in tail] == ['ActionModeConfig', 'ActionGraphConfig', 'ActionTouchEvent']
        assert (browser/'untouched.zip').read_bytes() == (browser/'undo.zip').read_bytes() == origin.read_bytes()
        assert members(browser/'redo.zip') == edited
        thumb = 'note/thumbnail.jpg'
        input_jpeg, web_jpeg, again_jpeg = (Image.open(BytesIO(f[thumb])) for f in (src, edited, twice))
        assert input_jpeg.size == ((320, 240) if version == 1 else (640, 480))
        assert web_jpeg.size == again_jpeg.size == (640, 480)
        baseline = work/f'backing-v{version}-source'
        source_graph = pixels(Image.open(baseline/'recorder.png'))
        base = {'original_ink', 'original_image'}
        once = base | {'first_edit'}
        plots = {'browser_open_vs_native_load': compare(source_graph, screen(browser/'before.png'), base),
                 'browser_reopen_vs_web_jpeg': compare(pixels(web_jpeg), screen(browser/'after.png'), once)}
        assert np.array_equal(pixels(input_jpeg), pixels(Image.open(baseline/'sidebar.png')))
        reports = []
        same_graph = (readers/'错题本/recorder.png').read_bytes()
        for name in ('错题本','优课畅学','新测评','随身答','again'):
            folder = readers/name
            report = json.loads((folder/'report.json').read_bytes())
            assert report['strokes'] == 0 and report['images'] == 1
            current = pixels(again_jpeg if name == 'again' else web_jpeg)
            assert np.array_equal(current, pixels(Image.open(folder/'sidebar.png')))
            if name == 'again':
                plots['native_second_open_vs_second_jpeg'] = compare(current, pixels(Image.open(folder/'recorder.png')), once | {'second_edit'})
            else:
                assert (folder/'recorder.png').read_bytes() == same_graph
                if name == '错题本':
                    plots['native_first_open_vs_first_jpeg'] = compare(current, pixels(Image.open(folder/'recorder.png')), once)
            reports.append({'stage': 'second_edit' if name == 'again' else 'first_edit', **report})
        result.append({'variant': version, 'input_jpeg_size': input_jpeg.size, 'export_jpeg_size': web_jpeg.size,
                       'input_zip_sha256': sha256(origin.read_bytes()).hexdigest(),
                       'first_edit_zip_sha256': sha256((browser/'web.zip').read_bytes()).hexdigest(),
                       'second_edit_zip_sha256': sha256((browser/'again.zip').read_bytes()).hexdigest(),
                       'changed_members_at_each_export': sorted(expected),
                       'preserved_action_counts_at_each_stage': [len(a) for a in actions],
                       'cloud_sidebar_rgb_matching_export': 640*480, 'plots': plots, 'readers': reports})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('work', type=Path)
    print(json.dumps(verify(**vars(parser.parse_args())), indent=2, ensure_ascii=False))
