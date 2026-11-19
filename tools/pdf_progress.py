"""Read the PdfEntity reading positions used by the two original PDF viewers."""
from sqlite_snapshot import open_snapshot


def decode(path):
    with open_snapshot(path) as db:
        db.execute('BEGIN')
        columns = {row[1]: row for row in db.execute('PRAGMA table_info("PdfEntity")')}
        required = {'id': 'TEXT', 'currentPage': 'INTEGER', 'pageCount': 'INTEGER'}
        if any(key not in columns or columns[key][2].upper() != sql_type for key, sql_type in required.items()):
            return None
        if columns['id'][5] != 1:
            return None
        entries = db.execute('SELECT id, currentPage, pageCount FROM PdfEntity ORDER BY id COLLATE BINARY')
        return {
            'format': 'pdf-progress',
            'user_version': db.execute('PRAGMA user_version').fetchone()[0],
            'documents': [
                {'path': path, 'current_page_index': page, 'page_count': count}
                for path, page, count in entries
            ],
        }
