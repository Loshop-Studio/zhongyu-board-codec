#!/usr/bin/env bash
# Build a local instrumentation app to read a Flutter export with the original APK's classes.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${JAVA_HOME:=/home/jdz/dev/jdk-21.0.13+9}"
: "${ANDROID_HOME:=/home/jdz/dev/android-sdk}"
export JAVA_HOME PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
serial=${1:?Supply the serial of a disposable emulator}
case "$serial" in emulator-*) ;; *) echo 'The harness expects an emulator serial' >&2; exit 1 ;; esac
bt="${BUILD_TOOLS:-$ANDROID_HOME/build-tools/35.0.0}"
platform="$ANDROID_HOME/platforms/android-35/android.jar"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/classes" "$work/dex" "$work/assets"
cat > "$work/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="local.zy.boardprobe">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/>
  <application android:label="Board format test" android:debuggable="true"><activity android:name=".PptWebViewProbe" android:exported="false"/></application>
  <instrumentation android:name=".ProbeRun" android:targetPackage="local.zy.boardprobe"/>
</manifest>
XML
javac --release 8 -Xlint:-options -cp "$platform" -d "$work/classes" tools/verification/{PageWriterProbe,PageReplayVariant,PageReplayProbe,PptRecorderProbe,PptGraphProbe,PptWebViewProbe,NoteBundleProbe,ArtworkCommandProbe,ArtworkVariantProbe,PageVariantProbe,BoardProbe,ProbeRun,NativeViewProbe,NativePlayerProbe}.java
"$bt/d8" --min-api 26 --lib "$platform" --output "$work/dex" "$work/classes/local/zy/boardprobe/"*.class
"$bt/d8" --min-api 26 --lib "$platform" --output "$work/assets/probe.jar" "$work/classes/BoardProbe.class" "$work/classes/NoteBundleProbe.class" "$work/classes/ArtworkCommandProbe.class" "$work/classes/PageReplayProbe.class" "$work/classes/PageReplayVariant.class" "$work/classes/ArtworkVariantProbe.class" "$work/classes/PageVariantProbe.class"
if [[ -n "${NEW_NOTE_ZIP:-}" ]]; then
  unzip -q "$NEW_NOTE_ZIP" -d "$work/assets/new-note"
fi
if [[ -n "${ARTWORK_EDIT_ZIP:-}" ]]; then
  unzip -q reports/evidence/board/artwork-edit-base.zip -d "$work/assets/art-base"
  unzip -q "$ARTWORK_EDIT_ZIP" -d "$work/assets/art-edited"
fi
if [[ -n "${NOTE_RESTORE_ZIP:-}" ]]; then
  unzip -q reports/evidence/board/native-note-bundle.zip -d "$work/assets/note-bundle"
  cp "$NOTE_RESTORE_ZIP" "$work/assets/edited-note.zip"
elif [[ -n "${NOTE_BUNDLE_DIR:-}" ]]; then
  cp -r "$NOTE_BUNDLE_DIR" "$work/assets/note-bundle"
fi
if [[ "${PAGE_WRITER:-}" == 1 ]]; then
  cp 中育apk/错题本.apk "$work/assets/mistake.apk"
  if [[ -n "${V6_REOPEN_ZIP:-}" ]]; then unzip -q "$V6_REOPEN_ZIP" -d "$work/assets/writer-input"; fi
elif [[ "${PPT_PROBE:-}" == 1 ]]; then
  unzip -q reports/evidence/board/web-sketch-presentation.zip -d "$work/assets/ppt-pages"
  if [[ -n "${PPT_NATIVE_EDIT:-}" ]]; then
    unzip -q "$PPT_NATIVE_EDIT" -d "$work/assets/ppt-pages"
  fi
  unzip -q reports/evidence/board/sketch-presentations.zip 'slides/res/ppt/*' -d "$work"
  mv "$work/slides/res/ppt" "$work/assets/ppt-fixture"
else
  mkdir -p "$work/assets/simple"
  cp reports/evidence/board/web-simple.bin "$work/assets/simple/"
  cp 中育apk/错题本.apk "$work/assets/mistake.apk"
  mkdir -p "$work/assets/transform-edit"
  cp reports/evidence/board/web-transform.bin "$work/assets/transform-edit/actions.bin"
  unzip -q reports/evidence/board/sketch-transform.zip -d "$work/assets"
  unzip -q reports/evidence/board/sketch-images.zip -d "$work/assets"
  unzip -q reports/evidence/board/sketch-image-recording.zip -d "$work/assets"
  unzip -q reports/evidence/board/sketch-image-versions.zip -d "$work/assets"
  if [[ -n "${SKETCH_IMAGE_EDIT:-}" ]]; then
    unzip -q "$SKETCH_IMAGE_EDIT" -d "$work/image-edit"
    mv "$work/image-edit/illustration" "$work/assets/image-edit"
  fi
  unzip -q reports/evidence/board/sketch-recording.zip -d "$work/assets"
  unzip -q reports/evidence/board/recording-edited.zip -d "$work/assets/browser-edit"
  unzip -q reports/evidence/board/web-page.zip -d "$work/assets"
fi
"$bt/aapt2" link --manifest "$work/AndroidManifest.xml" -I "$platform" -A "$work/assets" -o "$work/probe.apk"
python3 - "$work" "${PAGE_WRITER:-0}" <<'PYZIP'
from pathlib import Path
from zipfile import ZipFile
import sys
work = Path(sys.argv[1])
with ZipFile(work/'probe.apk', 'a') as output:
    output.write(work/'dex/classes.dex', 'classes.dex')
    if sys.argv[2] == '1':
        lib='lib/armeabi-v7a/libobjectbox-jni.so'
        with ZipFile(work/'assets/mistake.apk') as apk:
            output.writestr(lib,apk.read(lib))
PYZIP
"$bt/zipalign" -f 4 "$work/probe.apk" "$work/aligned.apk"
"$bt/apksigner" sign --ks .work/build/debug.jks --ks-pass pass:android --out "$work/signed.apk" "$work/aligned.apk"
adb -s "$serial" install -r "$work/signed.apk" >&2
if [[ "${PAGE_WRITER:-}" == 1 ]]; then
  : "${BOARD_EVIDENCE_DIR:?Set an output directory for the native recording}"
  timeArgs=()
  if [[ -n "${V6_PAPER_TIMES:-}" ]]; then
    [[ "$V6_PAPER_TIMES" =~ ^[0-9]+(,[0-9]+)*$ && -n "${V6_REOPEN_ZIP:-}" ]]
    timeArgs=(-e paperTimes "$V6_PAPER_TIMES")
  fi
  if [[ -n "${V6_PAUSE_CURSOR:-}" ]]; then
    [[ "$V6_PAUSE_CURSOR" =~ ^[0-9]+,[0-9]+,[[:xdigit:]]{8}$ && -n "${V6_PAPER_TIMES:-}" ]]
    timeArgs+=(-e pauseCursor "$V6_PAUSE_CURSOR")
  fi
  result=$(adb -s "$serial" shell am instrument -w -e pageWriter true -e forwardCamera "${V6_FORWARD_CAMERA:-0}" -e recordCamera "${V6_CAMERA:-0}" -e recordCursor "${V6_CURSOR:-0}" -e contentThumbnail "${V6_CONTENT_THUMBNAIL:-0}" -e scrollable "${V6_SCROLLABLE:-0}" -e ruledPaper "${V6_RULED_PAPER:-0}" "${timeArgs[@]}" local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  folder=$(sed -n 's/^INSTRUMENTATION_RESULT: saved=//p' <<< "$result" | tr -d '\r')
  [[ "$folder" =~ ^page-writer-[0-9]+$ ]]
  if [[ -n "${V6_PAPER_TIMES:-}" ]]; then
    mkdir -p "$BOARD_EVIDENCE_DIR"
    IFS=, read -ra times <<< "$V6_PAPER_TIMES"
    if [[ "${V6_FORWARD_CAMERA:-0}" == 1 ]]; then
      for t in "${times[@]}"; do
        adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-forward-$t.png" > "$BOARD_EVIDENCE_DIR/forward-$t.png"
      done
      for name in ended.png settled.png times.json; do
        adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$name" > "$BOARD_EVIDENCE_DIR/$name"
      done
      exit
    fi
    for t in "${times[@]}"; do
      adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-seek-$t.png" > "$BOARD_EVIDENCE_DIR/seek-$t.png"
    done
    if [[ -n "${V6_PAUSE_CURSOR:-}" ]]; then
      for stage in paused still ended; do
        adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$stage.png" > "$BOARD_EVIDENCE_DIR/$stage.png"
      done
    fi
    exit
  fi
  mkdir -p "$BOARD_EVIDENCE_DIR/note"
  adb -s "$serial" exec-out run-as local.zy.boardprobe tar -C "files/$folder" -cf - . | tar -C "$BOARD_EVIDENCE_DIR/note" -xf -
  adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder.png" > "$BOARD_EVIDENCE_DIR/android.png"
  if [[ "${V6_CAMERA:-0}" == 1 && -z "${V6_REOPEN_ZIP:-}" ]]; then
    for stage in zoom pan-0 pan-1 pan-2 pan-3 pan-up pinch-0 pinch-1 pinch-2 pinch-3 pinch-up; do
      adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$stage.png" > "$BOARD_EVIDENCE_DIR/$stage.png"
    done
  fi
  if [[ "${V6_CURSOR:-0}" == 1 && -z "${V6_REOPEN_ZIP:-}" ]]; then
    for tool in finger stylus; do
      for i in 0 1 2 3; do
        adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$tool-$i.png" > "$BOARD_EVIDENCE_DIR/$tool-$i.png"
      done
    done
  fi
  if [[ "${V6_RULED_PAPER:-0}" == 1 ]]; then
    adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-grid.png" > "$BOARD_EVIDENCE_DIR/grid.png"
    if [[ -z "${V6_REOPEN_ZIP:-}" ]]; then
      adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-lines.png" > "$BOARD_EVIDENCE_DIR/lines.png"
    fi
  fi
  if [[ -n "${V6_REOPEN_ZIP:-}" ]]; then
    for image in opened list content; do
      adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$image.png" > "$BOARD_EVIDENCE_DIR/$image.png"
    done
  fi
  exit
fi
if [[ "${PPT_PROBE:-}" == 1 ]]; then exit 0; fi
if [[ "${PAGE_REPLAY:-}" == 1 ]]; then
  result=$(adb -s "$serial" shell am instrument -w -e pageReplay true local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"native seeks"* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  if [[ -n "${BOARD_EVIDENCE_DIR:-}" ]]; then
    mkdir -p "$BOARD_EVIDENCE_DIR"
    adb -s "$serial" exec-out run-as local.zy.boardprobe tar -C files/page-replay -cf - . | tar -C "$BOARD_EVIDENCE_DIR" -xf -
  fi
  exit
fi
if [[ -n "${NEW_NOTE_ZIP:-}" ]]; then
  result=$(adb -s "$serial" shell am instrument -w -e newNotebook true local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"matching snapshot RGBA"* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  exit
fi
if [[ -n "${NOTE_RESTORE_ZIP:-}" ]]; then
  result=$(adb -s "$serial" shell am instrument -w -e noteRestore true local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"Flutter ZIP callbacks=1 identical files="* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  exit
fi
if [[ -n "${NOTE_BUNDLE_DIR:-}" ]]; then
  result=$(adb -s "$serial" shell am instrument -w -e noteBundle true local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"ZIP=lesson_upload.zip"* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  adb -s "$serial" exec-out run-as local.zy.boardprobe cat files/last-note.zip > "${NOTE_BUNDLE_OUTPUT:?Supply the path for the native zip}"
  exit
fi
if [[ -n "${ARTWORK_EDIT_ZIP:-}" ]]; then
  mode=artworkOnly
  evidence=artwork-edit-native.png
  if [[ "${ARTWORK_CREATE:-}" == 1 ]]; then mode=artworkCreate; evidence=artwork-create-native.png; fi
  if [[ "${ARTWORK_IMAGE:-}" == 1 ]]; then mode=artworkImage; evidence=page-image-native.png; fi
  result=$(adb -s "$serial" shell am instrument -w -e "$mode" true local.zy.boardprobe/.ProbeRun)
  echo "$result"
  [[ "$result" == *"native replay vs snapshot identical"* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
  if [[ -n "${BOARD_EVIDENCE_DIR:-}" ]]; then
    adb -s "$serial" exec-out run-as local.zy.boardprobe cat files/art-native.png > "$BOARD_EVIDENCE_DIR/$evidence"
  fi
  exit
fi
result=$(adb -s "$serial" shell am instrument -w local.zy.boardprobe/.ProbeRun)
echo "$result"
[[ "$result" == *"Verified native router, command, touch source, graph and source index"* && "$result" == *"INSTRUMENTATION_CODE: -1"* ]]
[[ "$result" == *"nativePlayer=700ms=1 900ms=0 950ms=1 1200ms=0 1200ms=0 1200ms=0 1950ms=1 2000ms=1"* ]]
[[ "$result" == *"editedRecording=durationMs=2000 strokes=2"* ]]
[[ "$result" == *"sketchTransforms=native transform frames="* ]]
if [[ -n "${BOARD_EVIDENCE_DIR:-}" ]]; then
  for folder in illustration image-recording image-edit image-v{2..5}; do
    if [[ -d "$work/assets/$folder" ]]; then
      for suffix in frames.json native.png; do
        adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$folder-$suffix" > "$BOARD_EVIDENCE_DIR/$folder-$suffix"
      done
    fi
  done
  for item in transform-frames.json transform-edit-frames.json transform-edit-native.png; do
    adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$item" > "$BOARD_EVIDENCE_DIR/$item"
  done
  for item in native-simple.png native-edited.bin native-simple-page.zip; do
    adb -s "$serial" exec-out run-as local.zy.boardprobe cat "files/$item" > "$BOARD_EVIDENCE_DIR/$item"
  done
fi
