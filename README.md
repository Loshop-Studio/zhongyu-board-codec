# Zhongyu board formats and Flutter editor

Open a local BIN, note ZIP or unpacked notebook directory and edit its supported content in the browser. The Dart codecs support SimpleBoard, Sketch V1–V5 and page-based Blackboard notes. Fixtures and original Android readback evidence accompany the [format and storage report](reports/画板与存储.md).

## Run the editor

From the repository root, use Flutter with the Dart SDK range in [pubspec.yaml](board_editor/pubspec.yaml).

```sh
cd board_editor
flutter pub get
flutter test
flutter build web --release --no-web-resources-cdn
python3 -m http.server 8765 --bind 127.0.0.1 --directory build/web
```

Open [the local editor](http://127.0.0.1:8765) and select **打开 BIN / ZIP**. Try the [Sketch V5 sample](reports/evidence/board/sketch-shapes/web.bin), [V1 notebook](reports/evidence/board/sketch-shapes/v1-web.zip) or [native Blackboard V6 notebook](reports/evidence/board/native-v6-recording.zip).

## Source and evidence

- [Flutter source and generated Protobuf bindings](board_editor/lib/)
- [Flutter regression tests](board_editor/test/)
- [Fixtures, browser exports and native comparisons](reports/evidence/board/)
- [Android readback evidence](reports/evidence/art/)
- [Browser and Android verification tools](tools/verification/)

Flutter tests use the files in this repository. The optional Android comparison probes load original APKs from `中育apk/` and use a disposable emulator. Input APKs and the corresponding build projects are available from the [Zhongyu repository](https://github.com/Loshop-Studio/zhongyu-android-reverse) and the [Linspirer repository](https://github.com/Loshop-Studio/linspirer-android-reverse).
