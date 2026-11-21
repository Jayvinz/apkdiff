[English](README.md) | [简体中文](README.zh-CN.md)

# @jayvinz/apkdiff-cli

Command line APK size diff tool. Installs the `apkdiff` executable.

## Install

```bash
npm install -g @jayvinz/apkdiff-cli
```

Node.js 18 or newer.

## Usage

```bash
apkdiff old.apk new.apk
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt --new-mapping new/mapping.txt \
  --detect-renames --format console,json,html,markdown -o report/
```

Options match the Python and JVM CLIs:

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

Without `--fail-on-regression`, changes never affect the exit code.

The installed binary is `apkdiff`; it can also be run without a global install:

```bash
npx @jayvinz/apkdiff-cli old.apk new.apk
```
