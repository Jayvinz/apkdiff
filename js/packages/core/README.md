[English](README.md) | [简体中文](README.zh-CN.md)

# @jayvinz/apkdiff-core

APK size diff core library (pure Node.js, zero runtime dependencies).

Attributes DEX bytes to classes, compares classes and resources between two APKs, and
renders console / JSON / HTML / Markdown reports.

## Install

```bash
npm install @jayvinz/apkdiff-core
```

Node.js 18 or newer.

## Usage

```ts
import {
  ApkDiff,
  loadMapping,
  analyzeApk,
  diffApks,
  writeJson,
  writeHtml,
  writeMarkdown,
} from '@jayvinz/apkdiff-core';

const oldApk = analyzeApk('old.apk', loadMapping('old/mapping.txt'));
const newApk = analyzeApk('new.apk', loadMapping('new/mapping.txt'));
const result = diffApks(oldApk, newApk, false, true);

writeJson(result, 'report/apkdiff.json', 'compressed');
writeHtml(result, 'report/apkdiff.html', 'compressed');
writeMarkdown(result, 'report/apkdiff.md', 'compressed');
```

`ApkDiff` is a namespace-style facade mirroring the JVM API:

```ts
const result = ApkDiff.diff(
  ApkDiff.analyze('old.apk', ApkDiff.mapping('old/mapping.txt')),
  ApkDiff.analyze('new.apk'),
  false,
  true,
);
```

Public API:

- `analyzeApk(path, mapping?, hashContent?)`
- `loadMapping(path)` / `Mapping.parse(path)`
- `diffApks(old, new, includeMeta?, detectRenames?)`
- `printConsole`, `buildJson`, `writeJson`, `writeHtml`, `writeMarkdown`
- `humanSize`, `humanDelta`
- data classes: `ApkAnalysis`, `ApkClass`, `ApkEntry`, `DexAnalysis`, `DexClass`, `Change`, `DiffResult`

Reports are byte-for-byte identical to the Python and JVM implementations.
