# apkdiff Node.js 实现

[English](README.md) | 简体中文

面向 Node.js 18+ 的 APK 体积 diff。`js/` 是 npm workspaces 仓库，包含两个包：

| 包 | 用途 |
| --- | --- |
| `@jayvinz/apkdiff-core` | 核心库，零运行时依赖 |
| `@jayvinz/apkdiff-cli` | CLI，安装 `apkdiff` 命令，依赖 core 包 |

报告与 Python、JVM 实现逐字节一致。TypeScript 源码编译为 CommonJS + `.d.ts`。

## 安装与构建

```bash
cd js
npm ci
npm run build
npm test
```

构建产物位于 `packages/core/dist` 和 `packages/cli/dist`，已被 git 忽略。

## 命令行

全局安装：

```bash
npm install -g @jayvinz/apkdiff-cli
apkdiff old.apk new.apk --detect-renames
```

也可以不安装：

```bash
npx @jayvinz/apkdiff-cli old.apk new.apk
node packages/cli/dist/cli.js old.apk new.apk --format console,json -o report/
```

参数与 Python/JVM CLI 一致（`--format`、`--output`、`--metric`、`--top`、`--full`、
`--include-meta`、`--detect-renames`、`--fail-on-regression`）。

## 作为库使用

```bash
npm install @jayvinz/apkdiff-core
```

```ts
import {
  ApkDiff,
  analyzeApk,
  diffApks,
  loadMapping,
  writeHtml,
  writeJson,
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
- 数据类：`ApkAnalysis`、`ApkClass`、`ApkEntry`、`DexAnalysis`、`DexClass`、`Change`、
  `DiffResult`、`SizeBreakdown`

包级文档：
[`packages/core/README.zh-CN.md`](packages/core/README.zh-CN.md)、
[`packages/cli/README.zh-CN.md`](packages/cli/README.zh-CN.md)。

## 测试

```bash
cd js
npm test
node --test --test-name-pattern "small fixture: class changes" tests/core.test.cjs   # 单个测试
```

共 23 个测试。`tests/cli.test.cjs` 还会把生成的 JSON/HTML/Markdown 与
`../py/report-complex` 做逐字节比对。

## 发布

```bash
cd js
npm run build
npm publish --workspace @jayvinz/apkdiff-core
npm publish --workspace @jayvinz/apkdiff-cli
```

两个包的 `publishConfig.access` 均为 `public`；先发布 core，再发布 CLI。
`npm pack --workspace ...` 可生成 tarball 做隔离安装测试。

发布 CI 在推送 `js-v<version>` tag（只发 Node.js）或 `v<version>` tag（三种实现全发）时上传到
npm。版本取自 tag，CI 会改写两个 workspace 的版本以及 CLI 对 `@jayvinz/apkdiff-core` 的依赖，
然后带 npm provenance 发布。工作流需要仓库 secret `NPM_TOKEN`；只有填入真实 npm token（以
`npm_` 开头）才会发布，否则跳过发布步骤，构建和测试仍会执行。

## 目录结构

```text
package.json / package-lock.json / tsconfig.base.json
packages/core/
  package.json / tsconfig.json / README.md / README.zh-CN.md
  src/
    apk.ts  dex.ts  zip.ts  diff.ts  mapping.ts
    report.ts  template.ts  json-writer.ts  util.ts  index.ts
packages/cli/
  package.json / tsconfig.json / README.md / README.zh-CN.md
  src/cli.ts
tests/
  core.test.cjs / cli.test.cjs   # 23 个测试
  fixtures/                      # fixture 副本
```

## 实现说明

- **零运行时依赖**。Node 没有内置 ZIP API，`zip.ts` 自行读取 central directory，并用
  `node:zlib` 解压条目。
- `dex.ts` 把 DEX 字节归属到类；共享池归给第一个引用者。
  `所有类字节 + unattributed == dex 大小`。
- 类变更比较语义指纹，而不是 dex 原始字节。
- `json-writer.ts` 输出确定性 pretty JSON；`FixedDecimal` 保留 Python 风格的 `0.0`、`12.3`
  格式，不要替换成 `JSON.stringify`。
- `template.ts` 精确内嵌 HTML 报告模板。
- 资源对比覆盖所有 APK 条目（XML、PNG/WebP、SVG、JSON/文本、SQLite DB assets、native `.so`、
  `resources.arsc`、manifest 等），按大小 / CRC / SHA-256 对比。
- 报告使用 LF 换行，并在 CLI 测试中与 Python 基线逐字节比对。