#!/usr/bin/env bash
# Verify a Chromium cursor export against the original APKs on a disposable Android emulator.
set -eu
cd "$(dirname "$0")/../.."
serial=${1:?Supply an emulator serial}
work=$(realpath -m "${2:?Supply a directory for the cursor evidence}")
case "$serial" in emulator-*) ;; *) echo "Select a disposable emulator" >&2; exit 1;; esac
mkdir -p "$work/release-browser"
cp reports/evidence/board/cursor/native.zip "$work/native.zip"
BOARD_OUTPUT="$work/release-browser" node tools/verification/browser-roundtrip.cjs --page-cursor
note="$work/release-browser/web.zip"
export PYTHONPATH="$PWD/tools/verification${PYTHONPATH:+:$PYTHONPATH}"
parameters=$(python - "$work" <<'PY'
import json, sys
from pathlib import Path
from verify_cursor_variants import gestures
work=Path(sys.argv[1])
trace=json.loads((work/'release-browser/trace.json').read_bytes())
_,duration,shapes=gestures(work/'release-browser/web.zip')
times=[r['target'] for r in trace['edited']]
print(','.join(str(n) for n in dict.fromkeys(times+[duration])))
mouse=shapes[2];point=mouse['points'][1]
print(f"{round(point['x'])},{round(point['y'])},{mouse['color'] & 0xffffffff:08x}")
PY
)
mapfile -t values <<< "$parameters"
play(){
  local input=$1 times=$2 output=$3 sample=${4:-}
  PAGE_WRITER=1 V6_REOPEN_ZIP="$input" V6_PAPER_TIMES="$times" V6_PAUSE_CURSOR="$sample" BOARD_EVIDENCE_DIR="$output" \
    bash tools/verification/verify_page.sh "$serial"
}
play "$work/native.zip" 700,850,970,1095,1200,1450,1560,1670,1820,2011,970 "$work/play"
play "$work/native.zip" 970 "$work/forward" 225,145,ffd03177
play "$note" "${values[0]}" "$work/release-player"
play "$note" "${values[0]}" "$work/forward-web" "${values[1]}"
python tools/verification/verify_cursor_variants.py "$serial" "$note" "$work/release-variants.json"
BOARD_IMPORT_ZIP="$note" BOARD_EVIDENCE_DIR="$work/release-cloud" \
  BOARD_EXPECT_COUNTS=PageEntity=1,TouchEventEntity=5,TouchInfoEntity=21,CommandInfoEntity=11 \
  bash tools/verification/verify_cloud_store.sh "$serial"
python tools/verification/check_cursor.py "$work" > "$work/comparison.json"
