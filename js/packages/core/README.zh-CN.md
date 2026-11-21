[English](README.md) | 简体中文

# @jayvinz/apkdiff-core

APK 体积 diff 核心库（纯 Node.js，零运行时依赖）。

把 DEX 字节归属到类，比较两个 APK 的类与资源，并渲染控制台 / JSON / HTML / Markdown 报告。

## 安装

```bash
npm install @jayvinz/apkdiff-core
```

需要 Node.js 18 或更高版本。

## 使用

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

`ApkDiff` 是命名空间式门面，与 JVM API 对应：

```ts
const result = ApkDiff.diff(
  ApkDiff.analyze('old.apk', ApkDiff.mapping('old/mapping.txt')),
  ApkDiff.analyze('new.apk'),
  false,
  true,
);
```

公开 API：

- `analyzeApk(path, mapping?, hashContent?)`
- `loadMapping(path)` / `Mapping.parse(path)`
- `diffApks(old, new, includeMeta?, detectRenames?)`
- `printConsole` / `buildJson` / `writeJson` / `writeHtml` / `writeMarkdown`
- `humanSize` / `humanDelta`
- 数据类：`ApkAnalysis`、`ApkClass`、`ApkEntry`、`DexAnalysis`、`DexClass`、`Change`、`DiffResult`

报告与 Python、JVM 实现逐字节一致。