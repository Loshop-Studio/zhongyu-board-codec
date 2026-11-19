"""Verify every embedded entity/property against the model recovered from the APK."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from objectbox_store import decode


def main():
    data = ROOT / "reports/evidence/board/page_mdb/data.mdb"
    decoded = decode(data)
    reference = json.loads((ROOT / "reports/apps/中育云笔记/objectbox-model.json").read_text())
    result = {e["name"]: e for e in decoded["entities"]}
    properties = 0
    for entity in reference["entities"]:
        e = result[entity["name"]]
        assert entity["identity"] == {"id": e["id"], "uid": e["uid"]}
        props = {(p["name"], p["type"], p["id"], p["uid"]) for p in e["properties"]}
        expected = {(p["name"], p["type"], p["identity"]["id"], p["identity"]["uid"])
                    for p in entity["properties"]}
        assert props == expected
        properties += len(props)
        assert len(e["rows"]) == 1 and e["rows"][0]["id"] == 1
    assert len(result) == 24 and properties == 140
    assert result["PageEntity"]["rows"][0] == {
        "id": 1, "dirName": "p-local", "isChange": True, "commandFileName": "1_command.bin",
        "commandIndex": 7, "blackBoardEntityId": 0, "recordEntityId": 0, "headerEntityId": 1,
    }
    assert result["TextInfoEntity"]["rows"][0] == {
        "id": 1, "width": 18.0, "color": -15654349, "textSize": 2.0, "style": 1,
        "content": "本地画板样本", "recordId": 0,
    }
    for name in ("AudioInfoEntity", "CommandInfoEntity"):
        assert result[name]["rows"][0]["data"] == {"hex": "0123ff00"}
    imported = decode(data.with_name("web-import.mdb"))
    rows = {e["name"]: e["rows"] for e in imported["entities"]}
    assert (rows["HeaderEntity"][0]["width"], rows["HeaderEntity"][0]["height"],
            rows["HeaderEntity"][0]["duration"]) == (800, 600, 875)
    assert rows["PageEntity"][0]["dirName"] == "p1" and rows["PageEntity"][0]["headerEntityId"] == 1
    assert rows["TextInfoEntity"][0]["content"] == "画板图元 / Blackboard"
    assert rows["FileInfoEntity"][0]["fileName"] == "tiles.png"
    assert len(rows["GeometryInfoEntity"]) == 2 and len(rows["GeometryPointFEntity"]) == 3
    assert len(rows["CommandInfoEntity"]) == len(rows["TouchEventEntity"]) == 1
    events = rows["TouchInfoEntity"]
    assert len(events) == 16 and [p["eventTime"] for p in events] == list(range(0, 121, 8))
    assert events[-1]["x"] > events[0]["x"] and events[-1]["y"] > events[0]["y"]
    print(f"Imported web page: {imported['rows_decoded']} native rows, 16 recorded coordinates, "
          "800 x 600, 875 ms, text, geometry and image reference verified.")
    print(f"Native file {data.stat().st_size} bytes, {len(result)} entity types, "
          f"{properties} property descriptors, {decoded['rows_decoded']} rows")
    print("Catalog names, IDs, UIDs and property types match the APK model.")
    print("Page relation, integer, boolean, text, floats and both byte vectors match the native fixture.")


if __name__ == "__main__":
    main()
