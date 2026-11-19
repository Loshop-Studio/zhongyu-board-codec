"""Open an offline SQLite snapshot and any associated journal without touching the source."""
from contextlib import closing, contextmanager
from pathlib import Path
import shutil
import sqlite3
import tempfile


@contextmanager
def open_snapshot(path):
    """Read a stable copy of a device database without creating sidecars beside the input."""
    source = Path(path).resolve(strict=True)
    journals = [f for suffix in ('-wal', '-journal')
                if (f := Path(str(source) + suffix)).is_file() and f.stat().st_size]
    if not journals:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            yield db
        return
    # SQLite may rebuild its shared-memory index or roll back a hot journal.
    # Do that work in scratch space, using the caller's consistent DB/journal pair.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / source.name
        for file in (source, *journals):
            shutil.copyfile(file, copy.parent / file.name)
        with closing(sqlite3.connect(copy)) as db:
            db.execute('PRAGMA query_only=ON')
            yield db
