[English](README.md) | [简体中文](README.zh-CN.md)

# apkdiff

Command line APK size diff tool. Installs the `apkdiff` executable.

## Install

```bash
pip install apkdiff
```

Python 3.7 or newer. This installs `apkdiff-core` automatically.

## Usage

```bash
apkdiff old.apk new.apk
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt --new-mapping new/mapping.txt \
  --detect-renames --format console,json,html,markdown -o report/
```

Options match the Python, JVM and Node.js CLIs:

| Option | Description |
| --- | --- |
| `--format` | `console,json,html,markdown` (default `console,json,html`) |
| `-o, --output` | Output directory (default `apkdiff-report`) |
| `--metric` | `compressed` (default) or `uncompressed` |
| `--top N` | Console rows per section (default 30) |
| `--full` | Show all rows |
| `--include-meta` | Include `META-INF/` in resource comparison |
| `--detect-renames` | Detect resources renamed without content changes |
| `--fail-on-regression` | Exit 1 when the new APK is larger |

`python -m apkdiff` is also supported after installation.
