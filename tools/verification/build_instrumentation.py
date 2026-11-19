"""Build a local single-instrumentation APK from its Java entry point."""
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.PIPE)


def build_probe(directory, sdk, package, source, *support):
    probe_name = source.stem
    tools = sdk / 'build-tools/35.0.0'
    platform = sdk / 'platforms/android-35/android.jar'
    manifest = directory / 'AndroidManifest.xml'
    manifest.write_text(f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}">
    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="29"/>
    <application android:debuggable="true"/>
    <instrumentation android:name=".{probe_name}" android:targetPackage="{package}"/>
</manifest>
''')
    run('javac', '--release', '8', '-cp', platform, '-d', directory, source, *support)
    run(tools/'d8', '--min-api', '26', '--lib', platform, '--output', directory,
        *sorted(directory.joinpath(*package.split('.')).glob('*.class')))
    probe = directory/'probe.apk'
    run(tools/'aapt2', 'link', '-I', platform, '--manifest', manifest, '-o', probe)
    with ZipFile(probe, 'a') as apk:
        apk.write(directory/'classes.dex', 'classes.dex')
    aligned, signed = directory/'aligned.apk', directory/'signed.apk'
    run(tools/'zipalign', '-f', '4', probe, aligned)
    run(tools/'apksigner', 'sign', '--ks', ROOT/'.work/build/debug.jks', '--ks-pass', 'pass:android',
        '--out', signed, aligned)
    return signed
