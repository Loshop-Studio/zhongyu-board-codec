#!/usr/bin/env python3
"""After verify_page.sh, exercise the five APKs' original Sketch players on the same edited BIN."""
import argparse
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "reports/evidence/board"
PACKAGE = "local.zy.boardprobe"
APPS = ("错题本", "优课畅学", "新测评", "随身答", "中育云笔记")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serial", help="Disposable emulator used for verify_page.sh")
    parser.add_argument("--images", action="store_true", help="Use the image export bundled using SKETCH_IMAGE_EDIT")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-"):
        parser.error("Supply an emulator serial")

    def adb(*command, **kwargs):
        return subprocess.run(["adb", "-s", args.serial, *command], stdout=subprocess.PIPE,
                              check=True, **kwargs).stdout

    def pixels(data):
        with Image.open(io.BytesIO(data)) as img:
            assert img.size == (640, 480)
            return img.convert("RGBA").tobytes()

    def results(name):
        return adb("exec-out", "run-as", PACKAGE, "cat", "files/" + name)

    artifact = "image-edit" if args.images else "transform-edit"
    reference = json.loads((BOARD / (artifact+"-frames.json")).read_text())
    picture = pixels((BOARD / (artifact+"-native.png")).read_bytes())
    assert len(reference[-1]["strokes"]) == 3 and len(set(picture)) > 2
    if args.images:
        assert sum(isinstance(item, dict) for item in reference[-1]["layers"]) == 3
    output = []
    for name in APPS:
        apk = (ROOT / "中育apk" / (name + ".apk")).read_bytes()
        # A fresh instrumentation process loads exactly one original class path.
        # Remove both outputs to ensure results cannot leak between runs.
        adb("shell", "run-as", PACKAGE, "rm", "-f", "files/" + artifact + "-frames.json",
            "files/" + artifact + "-native.png")
        adb("shell", "-T", f"run-as {PACKAGE} sh -c 'cat > files/player-variant.apk'", input=apk)
        log = adb("shell", "am", "instrument", "-w", "-e", "playerVariant", "true",
                  "-e", "withImages", str(args.images).lower(),
                  PACKAGE + "/.ProbeRun").decode()
        row = {"app": name, "apk_sha256": hashlib.sha256(apk).hexdigest()}
        if "INSTRUMENTATION_CODE: -1" in log and "native transform frames=" in log:
            frames = json.loads(results(artifact + "-frames.json"))
            rgba = pixels(results(artifact + "-native.png"))
            row.update(status="drawn", callbacks=len(frames), final_strokes=len(frames[-1]["strokes"]),
                       equal_frames=frames == reference, equal_rgba=rgba == picture,
                       rgba_sha256=hashlib.sha256(rgba).hexdigest())
        else:
            causes = re.findall(r"Caused by: ([^\n]+)", log)
            cause = causes[-1] if causes else log.strip()
            sites = re.findall(r"\bat (com\.zykj\.sketch\.[^\n]+)", log)
            row.update(status="load_failed", cause=cause, sketch_stack=sites)
        print(name, row["status"], row.get("cause", ""), flush=True)
        output.append(row)
    source = "web-sketch-images.zip" if args.images else "web-transform.bin"
    evidence = {"input_sha256": hashlib.sha256((BOARD / source).read_bytes()).hexdigest(),
                "input": source, "viewport": [640, 480], "players": output}
    report = "sketch-image-players.json" if args.images else "sketch-players.json"
    (ROOT / "reports/evidence/art" / report).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    for row in output:
        if row["app"] == "中育云笔记" and row["status"] == "load_failed":
            assert "makeExtensionsImmutable" in row["cause"], row
        else:
            assert row["status"] == "drawn" and row["equal_frames"] and row["equal_rgba"], row


if __name__ == "__main__":
    main()
