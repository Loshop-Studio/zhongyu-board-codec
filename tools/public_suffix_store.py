"""Read the two length-prefixed rule tables bundled with OkHttp on Android."""
import gzip
import zlib


def read_public_suffixes(path):
    with path.open('rb') as source:
        compressed = source.read(2) == b'\x1f\x8b'
        source.seek(0)
        if compressed:
            with gzip.GzipFile(fileobj=source) as stream:
                try:
                    tables = read_tables(stream)
                except zlib.error as error:
                    raise ValueError('invalid compressed public suffix database') from error
        else:
            tables = read_tables(source)
    return {'container': 'gzip' if compressed else 'raw', **tables}


def read_tables(stream):
    tables = {}
    for kind in ('rules', 'exceptions'):
        header = stream.read(4)
        if len(header) != 4:
            raise ValueError(f'missing {kind} length')
        length = int.from_bytes(header, 'big', signed=True)
        if length < 0:
            raise ValueError(f'invalid {kind} length')
        payload = stream.read(length)
        if len(payload) != length:
            raise ValueError(f'truncated {kind} table')
        if payload and not payload.endswith(b'\n'):
            raise ValueError(f'unterminated {kind} entry')
        tables[kind] = payload.decode('utf-8').split('\n')[:-1]
    if stream.read(1):
        raise ValueError('unexpected bytes after public suffix exceptions')
    return tables
