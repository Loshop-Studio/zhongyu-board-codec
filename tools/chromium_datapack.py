"""Read Chromium DataPack v5 resources, including aliases to shared payloads."""
import hashlib
import struct

HEADER = struct.Struct('<IB3xHH')
ENTRY = struct.Struct('<HI')
ALIAS = struct.Struct('<HH')
ENCODINGS = ('binary', 'utf-8', 'utf-16-le')
TBS_PACKS = {'libtbs.libresources.so.so', 'libtbs.libwebviewchromium.so.so',
             'libtbs.libzh_cn.so.so'}


class DataPack:
    def __init__(self, data):
        self.data = data
        if len(data) < HEADER.size:
            raise ValueError('incomplete DataPack header')
        version, encoding, count, aliases = HEADER.unpack_from(data)
        if version != 5 or encoding >= len(ENCODINGS):
            raise ValueError('expected a Chromium DataPack v5 header')
        self.encoding = ENCODINGS[encoding]
        alias_start = HEADER.size + (count + 1) * ENTRY.size
        data_start = alias_start + aliases * ALIAS.size
        if data_start > len(data):
            raise ValueError('incomplete DataPack index')
        entries = list(ENTRY.iter_unpack(data[HEADER.size:alias_start]))
        if entries[0][1] != data_start or entries[-1] != (0, len(data)):
            raise ValueError('DataPack payload boundaries disagree with index')
        self.entries = {}
        previous_id = -1
        for (resource_id, start), (_, end) in zip(entries, entries[1:]):
            if resource_id <= previous_id or start > end:
                raise ValueError('DataPack index is out of order')
            self.entries[resource_id] = (start, end)
            previous_id = resource_id
        self.aliases = {}
        for resource_id, index in ALIAS.iter_unpack(data[alias_start:data_start]):
            if resource_id in self.entries or resource_id in self.aliases or index >= count:
                raise ValueError('invalid DataPack alias')
            self.aliases[resource_id] = entries[index][0]

    def resource(self, resource_id):
        canonical = self.aliases.get(resource_id, resource_id)
        if canonical not in self.entries:
            raise ValueError(f'unknown DataPack resource ID {resource_id}')
        start, end = self.entries[canonical]
        return self.data[start:end]

    def inventory(self):
        resources = []
        for resource_id, (start, end) in self.entries.items():
            data = self.data[start:end]
            row = {'id': resource_id, 'offset': start, 'size': end - start,
                   'sha256': hashlib.sha256(data).hexdigest()}
            if data.startswith(b'\x1f\x8b'):
                row['type'] = 'gzip'
            elif data.startswith(b'\x89PNG\r\n\x1a\n'):
                row['type'] = 'PNG'
            elif data.startswith(b'fLaC'):
                row['type'] = 'FLAC'
            elif not data:
                row['type'] = 'empty'
            else:
                row['type'] = 'binary'
                if self.encoding != 'binary':
                    try:
                        row['text'] = data.decode(self.encoding)
                        row['type'] = 'text'
                    except UnicodeDecodeError:
                        pass
            resources.append(row)
        return {'format': 'Chromium DataPack v5', 'encoding': self.encoding,
                'resource_count': len(resources), 'alias_count': len(self.aliases),
                'resources': resources, 'aliases': self.aliases}
