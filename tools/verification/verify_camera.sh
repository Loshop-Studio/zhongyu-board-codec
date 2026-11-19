#!/usr/bin/env bash
# Read the Chromium export on a disposable Android emulator using the original APKs.
set -eu
cd "$(dirname "$0")/../.."
serial=${1:?Supply an emulator serial}
case "$serial" in emulator-*) ;; *) echo 'Select a disposable emulator' >&2; exit 1;; esac
work=$(realpath -m "${2:?Supply an output directory}")
mkdir -p "$work/browser"
export PYTHONPATH="$PWD/tools/verification${PYTHONPATH:+:$PYTHONPATH}"
BOARD_OUTPUT="$work/browser" node tools/verification/browser-roundtrip.cjs --page-camera
original="$PWD/reports/evidence/board/camera/native.zip"
edited="$work/browser/web.zip"
options=$(python - "$work" <<'PY'
import sys,json
from pathlib import Path
from verify_camera_variants import camera_commands
from check_native_page_recording import ROOT,schema_reader
w=Path(sys.argv[1])
files,duration,actions=camera_commands(w/'browser/web.zip')
trace=json.loads((w/'browser/trace.json').read_bytes())
for group,end in [('original',2557),('edited',duration)]:
    print(','.join(str(t) for t in sorted({r['target'] for r in trace[group]}|{end})))
p=schema_reader(ROOT/'中育apk/错题本.apk')
print(sum(len(p('CommandSource',files[r.fileName]).commandInfo) for r in p('RouterRecord',files['router.bin']).commandRecord))
print(sum(len(g['samples']) for g in actions))
PY
)
mapfile -t values <<< "$options"
play() {
    PAGE_WRITER=1 V6_REOPEN_ZIP="$1" V6_PAPER_TIMES="$2" V6_FORWARD_CAMERA="$3" BOARD_EVIDENCE_DIR="$work/$4" \
      bash tools/verification/verify_page.sh "$serial"
}
play "$original" "${values[0]}" 1 forward
play "$original" "${values[0]},1340" 0 direct
play "$edited" "${values[1]}" 1 forward-web
play "$edited" "${values[1]},1340" 0 direct-web
python tools/verification/verify_camera_variants.py "$serial" "$edited" "$work/variants.json"
python tools/verification/verify_camera_variants.py "$serial" "$work/browser/writing.zip" "$work/writing-variants.json"
BOARD_IMPORT_ZIP="$edited" BOARD_EVIDENCE_DIR="$work/cloud" \
  BOARD_EXPECT_COUNTS="PageEntity=1,CommandInfoEntity=${values[2]},MatrixEventEntity=4,MatrixInfoEntity=${values[3]}" \
  bash tools/verification/verify_cloud_store.sh "$serial"
python tools/verification/check_camera.py "$work" >"$work/comparison.json"
