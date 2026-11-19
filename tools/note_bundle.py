"""Compare an offline mistake-book ZIP with its fileList.json transfer manifest."""
from collections import Counter
import hashlib
import json
from pathlib import PurePosixPath
import re
from zipfile import ZipFile

def _root_url(rows, members):
    # The original reader receives the manifest URL. Offline, infer the directory
    # only from recognized board roots that are actually present beside the list.
    anchors = {'header.bin','page_router.bin','actions.bin'} & members
    candidates = set()
    for row in rows:
        prefix, _, name = row['url'].rpartition('/')
        if prefix and name in anchors:
            candidates.add(prefix+'/')
    # Both a page and its containing notebook can have a header.bin. Compare
    # complete member names before deciding which candidate describes this ZIP.
    if candidates:
        scores={c:sum(r['url'].startswith(c) and r['url'][len(c):] in members for r in rows) for c in candidates}
        best=max(scores.values())
        candidates={c for c,count in scores.items() if count==best}
    if len(candidates) != 1:
        raise ValueError('无法从画板根文件确定清单 URL 前缀，请用 --note-base 指定清单所在的 URL 目录')
    return candidates.pop()

def inspect(file, base=None):
    notes = []
    with ZipFile(file) as archive:
        paths = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(paths) != len(set(paths)):
            raise ValueError('ZIP 含有同名文件')
        manifests = [p for p in paths if PurePosixPath(p).name=='fileList.json']
        if not manifests:
            raise ValueError('ZIP 中没有 fileList.json')
        if base and len(manifests)!=1:
            raise ValueError('--note-base 适用于含一份 fileList.json 的笔记')
        for manifest in manifests:
            folder = manifest[:-len('fileList.json')]
            nested = [p[:-len('fileList.json')] for p in manifests if p!=manifest and p.startswith(folder)]
            members = {p[len(folder):] for p in paths if p.startswith(folder) and p!=manifest and
                       not any(p.startswith(n) for n in nested)}
            rows=json.loads(archive.read(manifest))
            if not isinstance(rows,list) or not all(isinstance(r,dict) and isinstance(r.get('url'),str) and
                    isinstance(r.get('md5'),str) and re.fullmatch('[a-fA-F0-9]{32}',r['md5']) for r in rows):
                raise ValueError('笔记清单需要包含 url 和 32 位 MD5 的记录数组')
            root = base.rstrip('/')+'/' if base else _root_url(rows,members) if rows else ''
            seen=set()
            files=[]
            for i,r in enumerate(rows):
                url, expected=r['url'],r['md5']
                if not url.startswith(root):
                    files.append(dict(index=i,status='outside_base'))
                    continue
                name=url[len(root):]
                if name in seen:
                    raise ValueError('同一文件在笔记清单中出现多次')
                seen.add(name)
                item=dict(path=name,expected_md5=expected)
                if name not in members:
                    item['status']='missing'
                else:
                    with archive.open(folder+name) as data:
                        actual=hashlib.file_digest(data,'md5').hexdigest().upper()
                    # NoteDownloadUtils compares to the uppercase digest as a string.
                    item.update(actual_md5=actual,status='match' if actual==expected else 'changed')
                files.append(item)
            extra=sorted(members-seen)
            notes.append(dict(manifest=manifest,counts=dict(Counter(f['status'] for f in files)),
                              unlisted=extra,files=files))
    return dict(format='mistake-note-bundle',notes=notes)
