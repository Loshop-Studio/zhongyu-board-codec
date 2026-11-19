"""Decode the ART P profile and V002 metadata formats found in the input APKs."""
from io import BytesIO
import struct
import zlib


def take(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated ART profile')
    return data


def numbers(stream, layout):
    return struct.unpack(layout, take(stream, struct.calcsize(layout)))


def delta_ids(stream, size):
    value = 0
    result = []
    for _ in range(size):
        delta, = numbers(stream, '<H')
        value += delta
        result.append(value)
    return result


def hot_methods(payload, method_count):
    stream = BytesIO(payload)
    result = {}
    current = 0
    while stream.tell() < len(payload):
        delta, num_caches = numbers(stream, '<HH')
        current += delta
        if current >= method_count:
            raise ValueError('hot method index exceeds DEX method count')
        caches = []
        for _ in range(num_caches):
            pc, mapping = numbers(stream, '<HB')
            cache = {'dex_pc': pc}
            if mapping in (6, 7):
                cache['kind'] = 'missing-types' if mapping == 6 else 'megamorphic'
            else:
                cache['types'] = []
                for _ in range(mapping):
                    dex, count = numbers(stream, '<BB')
                    types = list(numbers(stream, '<' + 'H' * count))
                    cache['types'].append({'dex_index': dex, 'type_ids': types})
            caches.append(cache)
        result[current] = caches
    return result


def profile_records(body, count):
    records = []
    for _ in range(count):
        key_size, classes, hot_size, crc, methods = numbers(body, '<HHIII')
        key = take(body, key_size).decode('utf-8')
        records.append({'key': key, 'class_count': classes, 'hot_region_bytes': hot_size,
                        'dex_checksum': crc, 'method_count': methods})
    for row in records:
        methods = row['method_count']
        row['hot_methods'] = hot_methods(take(body, row['hot_region_bytes']), methods)
        row['class_ids'] = delta_ids(body, row['class_count'])
        bitmap = take(body, (2 * methods + 7) // 8)
        for offset, label in ((0, 'startup'), (methods, 'post_startup')):
            row[label] = [i for i in range(methods)
                          if bitmap[(i + offset) // 8] & (1 << ((i + offset) % 8))]
    return records


def metadata_records(body, count):
    records = []
    for _ in range(count):
        index, key_size = numbers(body, '<HH')
        key = take(body, key_size).decode('utf-8')
        type_count, class_count = numbers(body, '<IH')
        records.append({'key': key, 'profile_index': index, 'type_count': type_count,
                        'class_ids': delta_ids(body, class_count)})
    return records


def decode(data):
    stream = BytesIO(data)
    header = take(stream, 8)
    if header == b'pro\x00010\x00':
        count, = numbers(stream, '<B')
        reader = profile_records
    elif header == b'prm\x00002\x00':
        count, = numbers(stream, '<H')
        reader = metadata_records
    else:
        raise ValueError('expected ART profile 010 or metadata 002')
    size, compressed_size = numbers(stream, '<II')
    compressed = take(stream, compressed_size)
    decompressor = zlib.decompressobj()
    try:
        decoded = decompressor.decompress(compressed, size + 1)
    except zlib.error as error:
        raise ValueError('invalid ART profile compression') from error
    if len(decoded) != size or not decompressor.eof or decompressor.unused_data or stream.read(1):
        raise ValueError('inconsistent ART profile length')
    body = BytesIO(decoded)
    records = reader(body, count)
    if body.read(1):
        raise ValueError('unexpected data after ART profile records')
    return {'version': header[4:7].decode('ascii'), 'uncompressed_bytes': size, 'dex': records}
