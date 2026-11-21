"""Compare a browser edit of the native two-page fixture with the original APK readback."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from objectbox_store import decode


def check(source, output, native_log):
    original = decode(source)
    result = decode(output)
    assert original.keys() == result.keys()
    assert {k: v for k, v in original.items() if k != 'entities'} == {
        k: v for k, v in result.items() if k != 'entities'}
    different = []
    tables = {}
    for old, new in zip(original['entities'], result['entities'], strict=True):
        assert {k: v for k, v in old.items() if k != 'rows'} == {k: v for k, v in new.items() if k != 'rows'}
        tables[new['name']] = new
        for a, b in zip(old['rows'], new['rows'], strict=True):
            assert a['id'] == b['id']
            different.extend((new['name'], b['id'], key) for key in a if a[key] != b[key])
    assert sorted(different) == sorted([('TouchEventEntity', 1, 'width'), ('TouchEventEntity', 1, 'color'),
                                         ('TouchInfoEntity', 2, 'x'), ('TouchInfoEntity', 2, 'y')]), different
    paint = tables['TouchEventEntity']['rows'][0]
    assert paint['width'] == 12 and paint['color'] & 0xffffffff == 0xffd32f2f
    ids = [b for a, b in tables['TouchEventEntity']['relations'][0]['pairs'] if a == 1]
    points = [r for r in tables['TouchInfoEntity']['rows'] if r['id'] in ids]
    assert math.dist([132, 100], [points[1]['x'], points[1]['y']]) <= 2
    report = dict(changed_fields=different, entity_types=result['catalog_entities'],
                  rows=result['rows_decoded'], relation_pairs=result['relation_pairs'])
    if native_log:
        fields = {}
        for line in native_log.read_text().splitlines():
            if line.startswith('INSTRUMENTATION_RESULT: '):
                key, value = line.removeprefix('INSTRUMENTATION_RESULT: ').split('=', 1)
                fields[key] = value
        assert int(fields['inkColor']) == paint['color'] and float(fields['inkWidth']) == paint['width']
        actual = json.loads(fields['inkPoints'])
        assert len(actual) == len(points)
        for values, row in zip(actual, points, strict=True):
            assert values[2] == row['eventTime']
            assert math.dist(values[:2], [row['x'], row['y']]) < .0001
        report['apk_readback'] = dict(width=paint['width'],color=hex(paint['color'] & 0xffffffff),points=actual)
    return report


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('edited', type=Path)
    args.add_argument('--source', type=Path, default=ROOT / 'reports/evidence/board/page_mdb/native-v6-two-pages.mdb')
    args.add_argument('--native-log', type=Path)
    a = args.parse_args()
    print(json.dumps(check(a.source, a.edited, a.native_log), indent=2))
