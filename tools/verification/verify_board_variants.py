#!/usr/bin/env python3
"""Compare Flutter exports with the generated parsers in five supplied APKs on Android ART."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "reports/evidence/board"
EVIDENCE = ROOT / "reports/evidence/art"
TYPES = {
    "header": ("Header.proto", "Header"),
    "pages": ("PageRouter.proto", "PageRouter"),
    "router": ("RouterRecord.proto", "RouterRecord"),
    "snapshot": ("GraphSnapshot.proto", "PageSnapshot"),
    "touch": ("Source.proto", "TouchSource"),
    "commands": ("Command.proto", "CommandSource"),
    "text": ("Source.proto", "TextSource"),
    "geometry": ("Source.proto", "GeometrySource"),
    "file": ("Source.proto", "FileSource"),
}
APPS = ["错题本", "优课畅学", "新测评", "随身答", "中育云笔记"]


def run(*cmd, data=None):
    return subprocess.run(cmd, input=data, stdout=subprocess.PIPE, check=True).stdout


def page_members():
    names = {"header.bin": "header", "page_router.bin": "pages",
             "router.bin": "router", "snapshot.bin": "snapshot"}
    parts = {"command": "commands", "touch": "touch", "file": "file",
             "geometry": "geometry", "text": "text"}
    members = {}
    with ZipFile(BOARD / "web-artwork.zip") as page:
        for entry in page.namelist():
            name = Path(entry).name
            key = names.get(name) or next(
                (value for suffix, value in parts.items() if name.endswith(f"_{suffix}.bin")), None)
            if key:
                members[key] = page.read(entry)
    assert members.keys() == TYPES.keys()
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial", help="Disposable Android emulator serial")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-"):
        parser.error("Supply an emulator serial")
    sdk = Path(os.environ["ANDROID_HOME"])
    platform = sdk / "platforms/android-35/android.jar"
    d8 = sdk / "build-tools/35.0.0/d8"
    app_dir = ROOT / "中育apk"
    src = Path(__file__).resolve().parent
    members = page_members()

    def adb(*cmd):
        return run(sdk / "platform-tools/adb", "-s", args.serial, *cmd)

    with tempfile.TemporaryDirectory(prefix="zy-format-") as tmp:
        work = Path(tmp)
        schemas = work / "schemas"
        schemas.mkdir()
        with ZipFile(app_dir / "错题本.apk") as apk:
            for name in apk.namelist():
                path = Path(name)
                if path.suffix != ".proto" or path.is_absolute() or ".." in path.parts:
                    continue
                target = schemas / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(apk.read(name).removeprefix(b"\xef\xbb\xbf"))
        run("javac", "--release", "8", "-cp", platform, "-d", work,
            src / "PageVariantProbe.java", src / "TimelineProbe.java")
        jar = work / "checks.jar"
        run(d8, "--min-api", "26", "--lib", platform, "--output", jar, *work.glob("*.class"))
        inputs = work / "inputs"
        inputs.mkdir()
        for name, content in members.items():
            (inputs / (name + ".bin")).write_bytes(content)
        with ZipFile(BOARD / "sketch-recording.zip") as recording:
            (inputs / "actions.bin").write_bytes(recording.read("recording/actions.bin"))
        remote = "/data/local/tmp/" + work.name
        adb("shell", "mkdir", remote)
        rows = []
        try:
            adb("push", jar, remote + "/")
            adb("push", inputs, remote + "/")
            for app in APPS:
                apk = app_dir / (app + ".apk")
                adb("push", apk, remote + "/original.apk")
                prefix = f"cd {remote} && CLASSPATH=checks.jar:original.apk app_process /system/bin "
                if app == "错题本":
                    trace = adb("shell", prefix + "TimelineProbe inputs/actions.bin").decode()
                    lines = [s for s in trace.splitlines() if s.startswith("Native V")]
                    assert len(lines) == 5 and all("progress=2000 ms" in s for s in lines)
                    (EVIDENCE / "sketch-timeline.txt").write_text("\n".join(lines) + "\n")
                result = {}
                for line in adb("shell", prefix + "PageVariantProbe inputs").decode().splitlines():
                    name, status, detail = line.split(" ", 2)
                    if name not in TYPES:
                        continue
                    if status != "OK":
                        raise RuntimeError(f"{app} {name}: {detail}")
                    payload = adb("exec-out", "cat", remote + "/inputs/" + name + ".out")
                    schema, message = TYPES[name]
                    cmd = ["protoc", "-I" + str(schemas), "-I/usr/include", "--decode=" + message, schema]
                    result[name] = {
                        "class_read": True, "equal_payload": members[name] == payload,
                        "equal_decoded_fields": run(*cmd, data=members[name]) == run(*cmd, data=payload),
                        "bytes": len(payload),
                    }
                assert result.keys() == TYPES.keys()
                assert all(r["equal_decoded_fields"] for r in result.values())
                rows.append({"app": app, "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
                             "original_parser_results": result})
                print(app, f"{len(result)}/{len(TYPES)}", flush=True)
        finally:
            adb("shell", "rm", "-r", remote)
    (EVIDENCE / "page-variants.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
