[English](README.md) | [简体中文](README.zh-CN.md)

# apkdiff-core

APK size diff core library (pure Python standard library, zero runtime dependencies).

Attributes DEX bytes to classes, compares classes and resources between two APKs, and
renders console / JSON / HTML / Markdown reports.

## Install

```bash
pip install apkdiff-core
```

Python 3.7 or newer.

## Usage

```python
from apkdiff_core import (
    analyze_apk,
    diff_apks,
    load_mapping,
    print_console,
    write_html,
    write_json,
    write_markdown,
)

old = analyze_apk("old.apk", load_mapping("old/mapping.txt"))
new = analyze_apk("new.apk", load_mapping("new/mapping.txt"))
result = diff_apks(old, new, include_meta=False, detect_renames=True)

print_console(result, metric="compressed", top=30)
write_json(result, "report/apkdiff.json", "compressed")
write_html(result, "report/apkdiff.html", "compressed")
write_markdown(result, "report/apkdiff.md", "compressed")
```

Public API:

- `analyze_apk(path, mapping=None, hash_content=True)`
- `load_mapping(path)` / `Mapping.parse(path)`
- `diff_apks(old, new, include_meta=False, detect_renames=False)`
- `print_console` / `build_json` / `write_json` / `write_html` / `write_markdown`
- `human_size` / `human_delta`
- data classes: `ApkAnalysis`, `ApkClass`, `ApkEntry`, `DexAnalysis`, `DexClass`, `Change`, `DiffResult`

Reports are byte-for-byte identical to the JVM and Node.js implementations.
