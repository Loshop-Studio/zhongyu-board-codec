"""Read local ZYKJ Room, OkDownload and FileDownloader SQLite snapshots."""
from pathlib import Path
import sqlite3
from sqlite_snapshot import open_snapshot

COLUMNS = ('id', 'downloadUrl', 'localPath', 'totalSize', 'downloadSize', 'verifyCode', 'flag')
FLAGS = {0: 'DOWNLOADING', 1: 'DOWNLOAD_SUCCESS'}
NAMES = {
    'download.db': ('download-room', {'download': COLUMNS, 'upload': ('id',)}),
    'okdownload-breakpoint.db': ('okdownload', {
        'breakpoint': ('id', 'url', 'parent_path'),
        'block': ('id', 'breakpoint_id', 'block_index', 'start_offset', 'content_length', 'current_offset'),
    }),
    'filedownloader.db': ('filedownloader', {'filedownloader': ('_id', 'url', 'path', 'status', 'sofar', 'total')}),
}


def decode(path, kind=None):
    """Return the decoded task tables, or None when auto-detection finds a different SQLite schema."""
    pattern = NAMES.get(Path(path).name) if kind is None else next(
        (p for p in NAMES.values() if p[0] == kind), None)
    if pattern is None:
        if kind is not None:
            raise ValueError(f'Unknown download database {kind}')
        return None

    family, requirements = pattern
    with open_snapshot(path) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        for table, required in requirements.items():
            actual = {row['name'] for row in db.execute(f'PRAGMA table_info("{table}")')}
            missing = set(required) - actual
            if missing:
                if kind is None:
                    return None
                raise ValueError(f'Unrecognized {table} schema, missing {sorted(missing)}')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def read(table, order, columns='*'):
            return [dict(row) for row in db.execute(f'SELECT {columns} FROM "{table}" ORDER BY {order}')]

        result = {'user_version': db.execute('PRAGMA user_version').fetchone()[0]}
        if family == 'download-room':
            rows = read('download', 'id', ','.join(COLUMNS))
            for row in rows:
                row['flagName'] = FLAGS.get(row['flag'])
            identity = None
            if 'room_master_table' in tables:
                found = db.execute('SELECT identity_hash FROM room_master_table WHERE id=42').fetchone()
                identity = found[0] if found else None
            result.update(room_identity=identity, download=rows, upload_ids=[r['id'] for r in read('upload','id','id')])
        elif family == 'okdownload':
            blocks = read('block', 'breakpoint_id, block_index, id')
            for block in blocks:
                start, progress = block['start_offset'], block['current_offset']
                block['next_file_offset'] = start + progress if start is not None and progress is not None else None
            result.update(breakpoint=read('breakpoint','id'), block=blocks,
                          response_filenames=read('okdownloadResponseFilename','url') if 'okdownloadResponseFilename' in tables else None,
                          dirty_ids=[r['id'] for r in read('taskFileDirty','id','id')] if 'taskFileDirty' in tables else None)
        else:
            connections = read('filedownloaderConnection','id, connectionIndex') if 'filedownloaderConnection' in tables else None
            for connection in connections or ():
                start, current = connection['startOffset'], connection['currentOffset']
                connection['downloaded_in_connection'] = current - start if start is not None and current is not None else None
            result.update(filedownloader=read('filedownloader','_id'), connections=connections)
        return result
