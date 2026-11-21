"""Inspect Cloud Note database snapshots and legacy page and resource manifests."""
from collections import defaultdict
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile, is_zipfile


def read_stores(path, selected=None, force_database=False):
    """Find the active page_mdb stores, including in wrapped notebook exports."""
    from objectbox_store import decode

    def result(stores):
        if len(stores) == 1:
            return stores[0]['database']
        return {'format': 'cloud-note-databases', 'stores': stores} if stores else None

    if path.is_dir():
        if (path / 'page_mdb').is_dir():
            folders = [path / 'page_mdb']
        elif path.name == 'page_mdb' or (path / 'data.mdb').is_file() or (path / 'lock.mdb').is_file():
            folders = [path]
        else:
            folders = sorted(p for p in path.rglob('page_mdb') if p.is_dir())
        stores = []
        for folder in folders:
            data = folder / 'data.mdb'
            if not data.is_file():
                raise ValueError(f'云笔记数据库目录缺少 data.mdb：{folder}')
            stores.append({'member': data.relative_to(path).as_posix(), 'database': decode(data, selected)})
        return result(stores)
    if path.name.lower() == 'lock.mdb':
        raise ValueError('lock.mdb 是锁文件，请打开同目录的 data.mdb')
    if path.suffix.lower() == '.mdb' or (force_database and not is_zipfile(path)):
        return decode(path, selected)
    if not is_zipfile(path):
        return None
    with ZipFile(path) as archive:
        # A page_mdb directory takes precedence even in a mixed BIN/MDB export.
        expected = set()
        candidates = defaultdict(list)
        for item in archive.infolist():
            parts = item.filename.split('/')
            if parts[-1] == 'data.mdb' and not item.is_dir():
                candidates[item.filename].append(item)
            if 'page_mdb' in parts[:-1]:
                expected.add('/'.join(parts[:parts.index('page_mdb') + 1] + ['data.mdb']))
        if not expected and 'data.mdb' in candidates:
            expected.add('data.mdb')
        if not expected:
            return None
        stores = []
        with TemporaryDirectory() as directory:
            local = Path(directory) / 'data.mdb'
            for name in sorted(expected):
                matches = candidates[name]
                if len(matches) != 1:
                    raise ValueError(f'ZIP 中的云笔记数据库缺失或重名：{name}')
                with archive.open(matches[0]) as source, local.open('wb') as target:
                    shutil.copyfileobj(source, target)
                stores.append({'member': name, 'database': decode(local, selected)})
        return result(stores)


def strings(raw):
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(p, str) and p.startswith('/') for p in value):
        raise ValueError('index.json 需要由 Android 绝对页面目录组成的数组')
    return value


def resources(raw):
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(r, dict) and
            isinstance(r.get('local'), str) and isinstance(r.get('service'), str) for r in value):
        raise ValueError('res.json 需要含 local 和 service 字符串的对象数组')
    return value


def source_root(paths, members, resource_paths=(), all_members=()):
    """Find the common Android directory whose relative names occur in the archive."""
    scores = defaultdict(lambda: (0, 0))
    for path in set(paths):
        for cut, char in enumerate(path):
            if char != '/':
                continue
            prefix, suffix = path[:cut + 1], path[cut + 1:]
            if suffix in members:
                count, length = scores[prefix]
                # Dart and Android String.length count UTF-16 code units.
                scores[prefix] = (count + 1, length + len(suffix.encode('utf-16-le', errors='surrogatepass')) // 2)
    if not scores:
        return None
    best = max(scores.values())
    winners = [prefix for prefix, score in scores.items() if score == best]
    if len(winners) > 1:
        counts = {
            prefix: sum(
                path.startswith(prefix) and path[len(prefix):] in all_members
                for path in set(resource_paths)
            )
            for prefix in winners
        }
        most_resources = max(counts.values())
        winners = [prefix for prefix in winners if counts[prefix] == most_resources]
    if len(winners) != 1:
        raise ValueError('云笔记页面目录有多个同等匹配的来源')
    return winners[0]


def inspect(files, read, explicit_dirs=()):
    roots = {}
    for name in files:
        if name.rsplit('/', 1)[-1] != 'index.json':
            continue
        root = name[:-len('index.json')]
        try:
            roots[root] = strings(read(name))
        except (ValueError, UnicodeError):
            if root + 'res.json' in files:
                raise
    if not roots:
        raise ValueError('没有可识别的云笔记 index.json')

    scopes = {root: set() for root in roots}
    entries = set(files) | {directory.rstrip('/') + '/' for directory in explicit_dirs}
    for name in entries:
        parent = name.rpartition('/')[0]
        while True:
            prefix = parent + '/' if parent else ''
            if prefix in roots:
                scopes[prefix].add(name[len(prefix):])
                break
            if not parent:
                break
            parent = parent.rpartition('/')[0]

    notes = []
    for root, order in sorted(roots.items()):
        members = scopes[root]
        assets = resources(read(root + 'res.json')) if 'res.json' in members else []
        sketches = {n[:-len('/actions.bin')] for n in members if n.endswith('/actions.bin')}
        directories = {n[:i] for n in members for i, c in enumerate(n) if c == '/'}
        local_paths = [r['local'] for r in assets]
        base = (
            source_root(order, sketches, local_paths, members)
            or source_root(order, directories, local_paths, members)
            or source_root(local_paths, members)
        )

        def relative(path):
            return path[len(base):] if base is not None and path.startswith(base) else None

        pages = []
        for path in order:
            directory = relative(path)
            pages.append({
                'android_path': path, 'directory': directory,
                'present': directory in directories,
                'sketch': directory + '/actions.bin' if directory in sketches else None,
            })
        rows = []
        for resource in assets:
            member = relative(resource['local'])
            rows.append({**resource, 'member': member, 'present': member in members})
        listed = {p['directory'] for p in pages}
        notes.append({
            'folder': root.rstrip('/'), 'android_base': base,
            'pages': pages, 'resources': rows,
            'unlisted_sketch_pages': sorted(sketches - listed),
        })
    return {'format': 'cloud-note-legacy-index', 'notes': notes}


def decode(file):
    file = Path(file)
    if file.is_dir() or file.name == 'index.json':
        folder = file if file.is_dir() else file.parent
        items = [f for f in folder.rglob('*') if not f.is_symlink()]
        names = {f.relative_to(folder).as_posix() for f in items if f.is_file()}
        dirs = {f.relative_to(folder).as_posix() for f in items if f.is_dir()}
        return inspect(names, lambda name: (folder / name).read_bytes(), dirs)
    with ZipFile(file) as archive:
        files = [f.filename for f in archive.infolist() if not f.is_dir()]
        if len(files) != len(set(files)):
            raise ValueError('ZIP 含有同名文件')
        dirs = [f.filename for f in archive.infolist() if f.is_dir()]
        return inspect(set(files), archive.read, dirs)


def resource_rank(path):
    parent, _, name = path.rpartition('/')
    if parent.rsplit('/', 1)[-1] == 'page_mdb' and name in ('data.mdb', 'lock.mdb'):
        return 0 if name == 'data.mdb' else 1
    return {'screenshot.png': 2, 'snapshot.bin': 3}.get(name, 4)


def room(file, marked=()):
    """Read both page list algorithms from the same read-only Room database."""
    import sqlite3
    from contextlib import closing

    def android_string(value):
        return value.encode('utf-16-be', errors='surrogatepass')

    def rank(row):
        return resource_rank(row['id']), android_string(row['id'])

    marked = set(marked)
    notes = []
    database = Path(file).resolve()
    uri = database.as_uri() + '?mode=ro'
    # A closed Android export contains only the checkpointed database. Its
    # stored WAL-mode header would otherwise create sidecars while reading it.
    # If a WAL accompanies the export, read its committed pages through SQLite.
    with database.open('rb') as stream:
        wal_mode = stream.read(20)[18:20] == b'\x02\x02'
    if wal_mode and not any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-shm')):
        uri += '&immutable=1'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        groups = db.execute(
            'SELECT userId, fileId, count(*) AS total FROM ResourceEntity '
            'GROUP BY userId, fileId ORDER BY userId, fileId'
        )
        for group in groups:
            user, note_id, total = group
            # ResourceDao.V declares no ORDER BY. The old editor keeps the
            # first cursor row for each name and uses a stable pageIndex sort.
            # Querying the original SQL also preserves its choice of index.
            by_page = defaultdict(list)
            cursor = db.execute(
                'SELECT * FROM ResourceEntity WHERE fileId=? AND userId=? AND wasDeleted=0',
                (note_id, user),
            )
            for row in cursor:
                by_page[row['pageName']].append(row)
            legacy = []
            pages = []
            for name, rows in by_page.items():
                first = rows[0]
                legacy.append({'page': name, 'index': first['pageIndex'], 'first_resource': first['id']})
                if name in marked:
                    continue
                rep = min(rows, key=rank)
                screenshots = [r['id'] for r in rows if r['id'].endswith('screenshot.png')]
                pages.append({
                    'page': name,
                    'index': rep['pageIndex'],
                    'representative': rep['id'],
                    'preview': max(screenshots, key=android_string) if screenshots else None,
                })
            legacy.sort(key=lambda page: page['index'])
            pages.sort(key=lambda page: (page['index'], android_string(page['page'])))
            notes.append({
                'user_id': user,
                'file_id': note_id,
                'row_count': total,
                'deleted_rows': total - sum(map(len, by_page.values())),
                'legacy_source': 'ResourceEntity' if legacy else 'index.json',
                'legacy_editor_pages': legacy,
                'pages': pages,
            })
    return {'format': 'cloud-note-room-resource-order', 'marker_directories': sorted(marked), 'notes': notes}
