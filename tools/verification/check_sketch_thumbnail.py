"""Compare original recorder graph pixels, Chromium's JPEG and the bitmap bound by Cloud Note."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image

from compare_sketch_render import paper_rectangle


def members(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}


def pixels(image):
    return np.asarray(image.convert('RGB'), dtype=np.int16)


def coverage(image):
    r, g, b = image.transpose(2, 0, 1)
    y = np.arange(r.shape[0])[:, None]
    return {
        'original_red_ink': (y < 155) & (r > g + 25) & (r > b + 18) & (g < 150),
        'new_dark_ink': (y > 316) & (image.max(2) < 165),
        'coloured_picture': (y > 200) & (y < 280) & (image.max(2) - image.min(2) > 48),
    }


def compare(reference, candidate):
    results = {}
    a, b = coverage(reference), coverage(candidate)
    for key in a:
        shared = int((a[key] & b[key]).sum())
        union = int((a[key] | b[key]).sum())
        assert union > 500 and shared / union > .93, (key, shared, union)
        y, x = np.where(b[key])
        results[key] = {'shared': shared, 'union': union, 'iou': shared / union,
                        'bounds': [int(x.min()), int(y.min()), int(x.max()), int(y.max())]}
    assert results['original_red_ink']['bounds'][0] == 50  # stroke starts at x=15, then gets clipped
    return results


def verify(created, baseline, browser, variants):
    original = members(created/'native.zip')
    changed = members(browser/'web.zip')
    assert changed.keys() == original.keys()
    altered = sorted(name for name in changed if original[name] != changed[name])
    assert altered == ['note/actions.bin', 'note/thumbnail.jpg']
    for filename in ('untouched.zip','undo.zip'):
        assert (browser/filename).read_bytes() == (created/'native.zip').read_bytes()
    assert members(browser/'redo.zip') == changed
    before, after = (Image.open(BytesIO(files['note/thumbnail.jpg'])) for files in (original, changed))
    assert before.size == after.size == (640,480)
    assert before.quantization == after.quantization and before.layer == after.layer
    assert np.array_equal(pixels(before), pixels(Image.open(created/'sidebar.png')))
    native = pixels(Image.open(variants/'错题本/recorder.png'))
    input_report = json.loads((baseline/'report.json').read_bytes())
    assert (input_report['strokes'], input_report['images']) == (1, 1)
    # Compare the two reloaded graphs. The live recorder still has its input
    # bitmap in memory before the resource's first JPEG compression.
    old = pixels(Image.open(baseline/'recorder.png'))
    assert not coverage(old)['new_dark_ink'].any()
    assert np.array_equal(old[:315],native[:315])  # edit below the original image and stroke
    jpg = pixels(after)
    expected_file = (variants/'错题本/recorder.jpg').read_bytes()
    reports = []
    for name in ('错题本','优课畅学','新测评','随身答','中育云笔记'):
        folder = variants/name
        result = json.loads((folder/'report.json').read_bytes())
        assert np.array_equal(jpg, pixels(Image.open(folder/'sidebar.png')))
        result['cloud_sidebar_pixels_matching_web_jpeg'] = int(jpg.shape[0]*jpg.shape[1])
        if name == '中育云笔记':
            assert 'makeExtensionsImmutable' in result['load_error']
        else:
            assert (result['strokes'],result['images']) == (2,1)
            assert np.array_equal(native, pixels(Image.open(folder/'recorder.png')))
            assert (folder/'recorder.jpg').read_bytes() == expected_file
            result['recorder_jpeg_sha256'] = sha256(expected_file).hexdigest()
            alpha = Image.open(folder/'alpha.jpg')
            result['alpha_0_64_128_255_rgb'] = [alpha.getpixel((x,16)) for x in [16,48,80,112]]
        reports.append(result)
    screen = Image.open(browser/'editor.png').convert('RGB')
    crop = paper_rectangle(screen)
    resized = screen.crop(crop).resize(after.size, Image.Resampling.LANCZOS)
    return {
        'original_zip_sha256': sha256((created/'native.zip').read_bytes()).hexdigest(),
        'web_zip_sha256': sha256((browser/'web.zip').read_bytes()).hexdigest(),
        'changed_members': altered, 'jpeg_size': after.size, 'jpeg_components': after.layer,
        'quantization_tables_equal': True, 'source_graph_reopened': input_report,
        'unchanged_reopened_graph_pixels_above_new_stroke': 315 * after.width,
        'web_decoded_jpeg_vs_recorder': compare(native,jpg),
        'browser_canvas_vs_recorder': compare(native,pixels(resized)),
        'browser_canvas_crop':crop,'readers': reports,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('created','baseline','browser','variants'):
        parser.add_argument(arg,type=Path)
    print(json.dumps(verify(**vars(parser.parse_args())),ensure_ascii=False,indent=2))
