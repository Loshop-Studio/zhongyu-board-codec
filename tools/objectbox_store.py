"""Read a closed page_mdb snapshot through LMDB and its embedded ObjectBox catalog."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from objectbox_model import Reader


def _pairs(path):
    # mdb_dump opens the database read-only. Keep any LMDB reader-lock file
    # beside a temporary link, including when the input directory is read-only.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "data.mdb"
        try:
            os.link(path, target)
        except OSError:
            shutil.copyfile(path, target)
        with subprocess.Popen(["mdb_dump", tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            for line in proc.stdout:
                if line.rstrip() == b"HEADER=END":
                    break
            for key in proc.stdout:
                if key.rstrip() == b"DATA=END":
                    break
                value = proc.stdout.readline()
                if not (key.startswith(b" ") and value.startswith(b" ")):
                    raise ValueError("Malformed LMDB dump")
                yield bytes.fromhex(key.decode()), bytes.fromhex(value.decode())
            if proc.wait() != 0:
                raise ValueError(proc.stderr.read().decode(errors="replace").strip())


def _descriptor(key, value):
    r = Reader(value)
    table = r.ptr(0)
    name = r.string(table, 10)
    if not name or r.number(table, 6, "I") != key:
        raise ValueError(f"Unexpected ObjectBox catalog entry {key}")
    properties = []
    for p in r.vector(table, 12):
        properties.append({
            "id": r.number(p, 6, "I"), "uid": str(r.number(p, 4, "q")),
            "name": r.string(p, 16), "type": r.number(p, 18, "H"),
        })
    relations = []
    for rel in r.vector(table, 24):
        if r.number(rel, 8, "I") != key:
            raise ValueError(f"Wrong relation owner in {name}")
        relations.append({"id": r.number(rel, 4, "I"), "uid": str(r.number(rel, 6, "q")),
                          "target_entity_id": r.number(rel, 10, "I"), "pairs": []})
    return {"id": key, "name": name, "uid": str(r.number(table, 4, "q")),
            "properties": properties, "relations": relations, "rows": []}


def _fields(data, properties):
    r = Reader(data)
    table = r.ptr(0)
    values = {}
    for prop in properties:
        kind = prop["type"]
        # Slot zero of the FlatBuffer table is property ID 1.
        field = 2 + 2 * prop["id"]
        if kind == 9:
            value = r.string(table, field)
        elif kind == 23:
            addr = r.field(table, field)
            value = None
            if addr is not None:
                offset = r.ptr(addr)
                size = r.read("I", offset)
                if offset + 4 + size > len(data):
                    raise ValueError("Truncated ObjectBox byte vector")
                value = {"hex": data[offset+4:offset+4+size].hex()}
        elif kind == 1:
            value = bool(r.number(table, field, "B"))
        else:
            scalar = {5: "i", 6: "q", 7: "f", 11: "Q"}.get(kind)
            if scalar is None:
                raise ValueError(f"Unrecognised ObjectBox property type {kind}")
            value = r.number(table, field, scalar)
        values[prop["name"]] = value
    return values


def decode(path, selected=None):
    catalog = {}
    rows_read = 0
    forward, reverse = set(), set()
    other_relation_keys = 0
    for key, value in _pairs(path):
        # The compact standalone ToMany index stores (tag, owner, target)
        # in big-endian order and mirrors every pair with its endpoints swapped.
        if key and key[0] >> 2 == 2:
            if len(key) == 12 and not value:
                tag, first, second = struct.unpack(">III", key)
                flag = tag & 3
                relation = (tag & 0x03ffffff) >> 2
                if flag in (0, 2):
                    if flag == 0:
                        forward.add((relation, first, second))
                    else:
                        reverse.add((relation, second, first))
                    continue
            other_relation_keys += 1
            continue
        if len(key) != 8:
            continue
        packed = int.from_bytes(key, "big")
        if packed == 0:
            continue
        try:
            if packed < (1 << 32):
                catalog[packed] = _descriptor(packed, value)
            elif packed >> 58 == 6:
                entity_id = (packed & ((1 << 58) - 1)) >> 34
                entity = catalog.get(entity_id)
                if entity is None:
                    raise ValueError(f"ObjectBox row references unknown entity {entity_id}")
                if selected and selected != entity["name"]:
                    continue
                fields = _fields(value, entity["properties"])
                if fields.get("id") != packed & ((1 << 34) - 1):
                    raise ValueError(f'Mismatched object ID in {entity["name"]}')
                entity["rows"].append(fields)
                rows_read += 1
        except (IndexError, struct.error, UnicodeError) as error:
            raise ValueError("Unexpected ObjectBox page_mdb record layout") from error
    if not catalog:
        raise ValueError("ObjectBox entity descriptors were not found")
    if forward != reverse:
        if not other_relation_keys:
            raise ValueError("ObjectBox relation entries disagree with their reverse index")
        # Retain only pairs independently confirmed by this compact encoding.
        other_relation_keys += len(forward ^ reverse)
        forward &= reverse
    relations = {r["id"]: r for e in catalog.values() for r in e["relations"]}
    for rel in relations.values():
        if rel["target_entity_id"] not in catalog:
            raise ValueError(f'Missing target of ObjectBox relation {rel["id"]}')
        rel["target_entity"] = catalog[rel["target_entity_id"]]["name"]
    for relation, owner, target in sorted(forward):
        if relation not in relations:
            raise ValueError(f"Unknown ObjectBox relation {relation}")
        relations[relation]["pairs"].append([owner, target])
    entities = [e for e in catalog.values() if not selected or e["name"] == selected]
    if selected and not entities:
        raise ValueError(f"No entity named {selected}")
    return {"format": "ObjectBox page_mdb", "catalog_entities": len(catalog),
            "rows_decoded": rows_read, "relation_pairs": len(forward),
            "unparsed_relation_keys": other_relation_keys, "entities": entities}
