# apkdiff Python implementation

[English](README.md) | [简体中文](README.zh-CN.md)

APK size diff implementation in pure Python (standard library only, no runtime dependencies).
It is split into two PyPI packages:

| PyPI package | Import name | Purpose |
| --- | --- | --- |
| `apkdiff-core` | `apkdiff_core` | Core library, usable as a dependency |
| `apkdiff` | `apkdiff` | CLI, depends on `apkdiff-core`, installs the `apkdiff` command |

All three implementations (Python / JVM / Node.js) produce byte-identical reports.

## Requirements

- Python 3.7 – 3.14. The minimum is 3.7 because the code uses built-in `dataclasses` and
  `from __future__ import annotations`; all 15 tests pass on 3.7.9, 3.8–3.14.
- Python 3.6 and earlier are not supported (missing built-in dataclasses / future annotations);
  Python 3.0 is long EOL and modern pip/setuptools cannot install on it.

## Install and run

```bash
pip install apkdiff
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt \
  --new-mapping new/mapping.txt \
  --format console,json,html,markdown \
  -o report/
```

If mapping paths are omitted, the CLI looks for `<apk-name>-mapping.txt`,
`<apk-name>.mapping.txt`, or `mapping.txt` next to each APK.

`python -m apkdiff ...` is also supported.

## Library usage

```bash
pip install apkdiff-core
```

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

- `analyze_apk(path, mapping=None, hash_content=True)` → `ApkAnalysis`
- `load_mapping(path)` / `Mapping.parse(path)`
- `diff_apks(old, new, include_meta=False, detect_renames=False)` → `DiffResult`
- `print_console` / `build_json` / `write_json` / `write_html` / `write_markdown`
- `human_size` / `human_delta`
- data classes: `ApkAnalysis`, `ApkClass`, `ApkEntry`, `DexAnalysis`, `DexClass`, `Change`,
  `DiffResult`, `SizeBreakdown`

## CLI options

| Option | Description |
| --- | --- |
| `--format` | `console,json,html,markdown`; default `console,json,html` |
| `-o, --output` | Report directory; default `apkdiff-report` |
| `--metric` | `compressed` (default) or `uncompressed` |
| `--top N` | Console rows per section; default 30 |
| `--full` | Show all rows |
| `--include-meta` | Include `META-INF/` in resource comparison |
| `--detect-renames` | Report identical-content delete + add as a rename |
| `--fail-on-regression` | Exit 1 when the new APK is larger |

## Development and tests

```bash
cd py
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e packages/core -e packages/cli

python -m unittest discover -s tests -v
python -m unittest tests.test_apkdiff.TestDiff.test_class_changes -v   # single test
```

Tests read the committed fixture APKs and skip automatically if fixtures are missing.

## Build and publish

```bash
cd py
pip install build twine
python -m build packages/core
python -m build packages/cli
twine upload packages/core/dist/* packages/cli/dist/*   # requires a PyPI token
```

Both packages use version `1.0.0`; `apkdiff` depends on `apkdiff-core==1.0.0`.
`pip install apkdiff` has been verified from a local wheel index.

Release CI publishes to PyPI on a `py-v<version>` tag (Python only) or a bare `v<version>` tag
(all three implementations). The tag supplies the version and CI stamps it into both
`__version__` fields and the `apkdiff-core` dependency pin; no source version bump is needed.
The workflow needs the `PYPI_API_TOKEN` repository secret.

## Layout

```text
packages/core/
  pyproject.toml
  README.md / README.zh-CN.md
  src/apkdiff_core/
    __init__.py  apk.py  dex.py  diff.py  mapping.py  report.py  util.py
packages/cli/
  pyproject.toml
  README.md / README.zh-CN.md
  src/apkdiff/
    __init__.py  __main__.py  cli.py
tests/
  make_fixtures.py / make_complex_fixture.py
  check_size_regression.py
  fixtures/       # generated APKs, mappings, expected.json
  test_apkdiff.py # 15 tests
report-complex/   # sample reports; canonical baseline for cross-language parity
```

## Implementation notes

- `dex.py` attributes DEX bytes to classes; shared pools go to the first referencing class.
  `sum(class bytes) + unattributed == dex size`.
- Class changes compare semantic fingerprints, not raw dex bytes.
- Resource comparison covers every zip entry: XML, PNG/WebP, SVG, JSON/text, SQLite `.db` assets,
  native `.so`, `resources.arsc`, `AndroidManifest.xml`, etc., by size / CRC / SHA-256.
- Reports use LF line endings. JSON stores exact integer byte counts; console/HTML/Markdown show
  KB with two decimals.

See the package READMEs for API-specific details:
[`packages/core/README.md`](packages/core/README.md) and
[`packages/cli/README.md`](packages/cli/README.md).