#!/usr/bin/env bash
# Reproduce the native page_mdb writer on an emulator with 32-bit ARM support.
set -euo pipefail
cd "$(dirname "$0")/../.."
serial=${1:?Supply a disposable emulator serial}
case "$serial" in emulator-*) ;; *) exit 2 ;; esac
: "${JAVA_HOME:=/home/jdz/dev/jdk-21.0.13+9}"
: "${ANDROID_HOME:=/home/jdz/dev/android-sdk}"
export JAVA_HOME PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
bt="$ANDROID_HOME/build-tools/35.0.0"
platform="$ANDROID_HOME/platforms/android-35/android.jar"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/classes" "$work/assets" "$work/dex"
cat > "$work/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="local.zy.cloudstore">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/>
  <application android:label="Local board DB fixture" android:extractNativeLibs="true" android:debuggable="true"/>
  <instrumentation android:name=".CloudStoreProbe" android:targetPackage="local.zy.cloudstore"/>
</manifest>
XML
javac --release 8 -Xlint:-options -cp "$platform" -d "$work/classes" tools/verification/CloudStoreProbe.java
"$bt/d8" --min-api 26 --lib "$platform" --output "$work/dex" "$work/classes/local/zy/cloudstore/CloudStoreProbe.class"
if [[ -n "${BOARD_READBACK_MDB:-}" ]]; then
    cp "$BOARD_READBACK_MDB" "$work/assets/ink.mdb"
else
notebook=${BOARD_IMPORT_ZIP:-reports/evidence/board/web-cloud-note.zip}
if unzip -Z1 "$notebook" 'page_router.bin' >/dev/null 2>&1; then
    unzip -q "$notebook" -d "$work/assets/lesson"
else
    unzip -q "$notebook" -d "$work/assets"
fi
python3 - "$work/assets/entities.txt" <<'PYMODEL'
import json,sys
from pathlib import Path
model=json.loads(Path('reports/apps/中育云笔记/objectbox-model.json').read_text())
p=Path(sys.argv[1])
p.write_text('\n'.join(e['name'] for e in model['entities']))
names={e['identity']['id']:e['name'] for e in model['entities']}
p.with_name('relations.tsv').write_text('\n'.join('\t'.join([e['name'],r['name'],names[r['target']['id']]]) for e in model['entities'] for r in e['relations']))
PYMODEL
fi
cp "${BOARD_CLOUD_APK:-中育apk/中育云笔记.apk}" "$work/assets/cloud.apk"
"$bt/aapt2" link -I "$platform" --manifest "$work/AndroidManifest.xml" -A "$work/assets" -o "$work/app.apk"
python3 - "$work" <<'PY'
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import sys
work=Path(sys.argv[1])
lib='lib/armeabi-v7a/libobjectbox-jni.so'
with ZipFile(work/'assets/cloud.apk') as src,ZipFile(work/'app.apk','a') as out:
    out.write(work/'dex/classes.dex','classes.dex')
    out.writestr(lib,src.read(lib),compress_type=ZIP_DEFLATED)
PY
"$bt/zipalign" -f 4 "$work/app.apk" "$work/aligned.apk"
"$bt/apksigner" sign --ks "${BOARD_PROBE_KEYSTORE:-.work/build/debug.jks}" --ks-pass pass:android --out "$work/signed.apk" "$work/aligned.apk"
adb -s "$serial" install -r "$work/signed.apk" >&2
if [[ -n "${BOARD_READBACK_MDB:-}" ]]; then
    result=$(adb -s "$serial" shell am instrument -w local.zy.cloudstore/.CloudStoreProbe)
    echo "$result"
    [[ "$result" == *'INSTRUMENTATION_CODE: -1'* && "$result" == *'inkPoints='* ]]
    exit
fi
# Only the local fixture app is reset to give its two new entities reproducible IDs.
adb -s "$serial" shell pm clear local.zy.cloudstore >&2
result=$(adb -s "$serial" shell am instrument -w -e relations "${BOARD_RELATION_TEST:-0}" local.zy.cloudstore/.CloudStoreProbe)
echo "$result"
[[ "$result" == *'INSTRUMENTATION_CODE: -1'* && "$result" == *'本地画板样本'* && "$result" == *'reopenedEntityTypes=24'* ]]
if [[ "${BOARD_RELATION_TEST:-0}" == 1 ]]; then
    [[ "$result" == *"reopenedRelationPairs=33"* ]]
fi
counts=$(sed -n 's/^INSTRUMENTATION_RESULT: webPageImport=//p' <<< "$result")
python3 - "$counts" "${BOARD_EXPECT_COUNTS:-}" <<'PYCHECK'
import sys
counts = dict(pair.split('=') for pair in sys.argv[1].split())
if sys.argv[2]:
    for pair in sys.argv[2].split(','):
        key, expected = pair.split('=')
        assert counts[key] == expected, (key, counts[key], expected)
else:
    assert counts['PageEntity'] == '1'
    for key in ['CommandInfoEntity','TouchInfoEntity','TouchEventEntity','TextInfoEntity','GeometryInfoEntity','FileInfoEntity']:
        assert int(counts[key]) > 0, key
PYCHECK
if [[ -n "${BOARD_EVIDENCE_DIR:-}" ]]; then
    mkdir -p "$BOARD_EVIDENCE_DIR/page_mdb"
    adb -s "$serial" exec-out run-as local.zy.cloudstore cat files/page_mdb/data.mdb > "$BOARD_EVIDENCE_DIR/page_mdb/data.mdb"
    adb -s "$serial" exec-out run-as local.zy.cloudstore cat files/lesson/page_mdb/data.mdb > "$BOARD_EVIDENCE_DIR/page_mdb/web-import.mdb"
fi
