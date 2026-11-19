"""Read a DiskLruCache journal and compare committed sizes with its sibling files."""
from pathlib import Path


def decode(path):
    entries = {}
    dirty = set()
    events = dict.fromkeys(("CLEAN", "DIRTY", "REMOVE", "READ"), 0)
    incomplete_tail = False
    with Path(path).open("rb") as stream:
        header = [stream.readline().decode("ascii").rstrip("\r\n") for _ in range(4)]
        if header[:2] != ["libcore.io.DiskLruCache", "1"] or stream.readline() not in (b"\n", b"\r\n"):
            raise ValueError("Invalid DiskLruCache header")
        app_version, count = map(int, header[2:])
        if count < 1:
            raise ValueError("Expected positive value count")
        for number, line in enumerate(stream, 6):
            if not line.endswith(b"\n"):
                incomplete_tail = True
                break
            parts = line.decode("ascii").rstrip("\r\n").split(" ")
            if len(parts) < 2 or parts[0] not in events or not parts[1]:
                raise ValueError(f"Invalid journal record at line {number}")
            op, key, *lengths = parts
            if "/" in key or "\\" in key or "\x00" in key:
                raise ValueError(f"Invalid cache filename at line {number}")
            if len(lengths) != (count if op == "CLEAN" else 0):
                raise ValueError(f"Invalid byte counts at line {number}")
            events[op] += 1
            if op == "CLEAN":
                if not all(length.isdecimal() for length in lengths):
                    raise ValueError(f"Invalid byte count at line {number}")
                entries[key] = [int(length) for length in lengths]
                dirty.discard(key)
            elif op == "DIRTY":
                dirty.add(key)
            elif op == "REMOVE":
                entries.pop(key, None)
                dirty.discard(key)
    rows = []
    for key, lengths in entries.items():
        if key in dirty:
            continue
        slots = []
        for index, length in enumerate(lengths):
            file = Path(path).parent / f"{key}.{index}"
            size = file.stat().st_size if file.is_file() and not file.is_symlink() else None
            slots.append({"name": file.name, "recorded_bytes": length, "file_bytes": size})
        rows.append({"key": key, "slots": slots})
    return {"format": "libcore.io.DiskLruCache", "journal_version": 1,
            "app_version": app_version, "value_count": count, "events": events,
            "incomplete_tail": incomplete_tail, "pending_keys": sorted(dirty), "entries": rows}
