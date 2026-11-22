# apkdiff Node.js implementation

[English](README.md) | [简体中文](README.zh-CN.md)

APK size diff implementation for Node.js 18+. `js/` is an npm workspaces repository with two
packages:

| Package | Purpose |
| --- | --- |
| `@jayvinz/apkdiff-core` | Core library, zero runtime dependencies (import name `@jayvinz/apkdiff-core`) |
| `@jayvinz/apkdiff-cli` | CLI; installs the `apkdiff` executable and depends on the core package |

Reports are byte-identical to the Python and JVM implementations. The TypeScript sources compile
to CommonJS plus `.d.ts` declarations.

## Install and build

```bash
cd js
npm ci
npm run build
npm test
```

The build writes `packages/core/dist` and `packages/cli/dist`; generated output is ignored by git.

## CLI

Install globally:

```bash
npm install -g @jayvinz/apkdiff-cli
apkdiff old.apk new.apk --detect-renames
```

Or run without installing:

```bash
npx @jayvinz/apkdiff-cli old.apk new.apk
node packages/cli/dist/cli.js old.apk new.apk --format console,json -o report/
```

Options match the Python/JVM CLIs (`--format`, `--output`, `--metric`, `--top`, `--full`,
`--include-meta`, `--detect-renames`, `--fail-on-regression`).

## Library usage

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
- `printConsole` / `buildJson` / `writeJson` / `writeHtml` / `writeMarkdown`
- `humanSize` / `humanDelta`
- data classes: `ApkAnalysis`, `ApkClass`, `ApkEntry`, `DexAnalysis`, `DexClass`, `Change`,
  `DiffResult`, `SizeBreakdown`

Package-level docs:
[`packages/core/README.md`](packages/core/README.md),
[`packages/cli/README.md`](packages/cli/README.md).

## Tests

```bash
cd js
npm test
node --test --test-name-pattern "small fixture: class changes" tests/core.test.cjs   # single test
```

23 tests. `tests/cli.test.cjs` also compares generated JSON/HTML/Markdown against
`../py/report-complex` byte-for-byte.

## Publish

```bash
cd js
npm run build
npm publish --workspace @jayvinz/apkdiff-core
npm publish --workspace @jayvinz/apkdiff-cli
```

Both packages set `publishConfig.access` to `public`. Publish core before the CLI.
`npm pack --workspace ...` creates tarballs for isolated install tests.

Release CI publishes to npm on a `js-v<version>` tag (JS only) or a bare `v<version>` tag (all
three implementations). The tag supplies the version; CI rewrites both workspace versions and the
CLI's `@jayvinz/apkdiff-core` dependency before publishing with npm provenance. The workflow needs
the `NPM_TOKEN` repository secret; publishing runs only when the value is a real npm token
(starts with `npm_`), otherwise the publish step is skipped while build and tests still run.

## Layout

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
  core.test.cjs / cli.test.cjs   # 23 tests
  fixtures/                      # fixture copy
```

## Implementation notes

- **Zero runtime dependencies.** Node has no ZIP API, so `zip.ts` reads the central directory
  and inflates entries with `node:zlib`.
- `dex.ts` attributes DEX bytes to classes; shared pools go to the first referencing class.
  `sum(class bytes) + unattributed == dex size`.
- Class changes compare semantic fingerprints, not raw dex bytes.
- `json-writer.ts` writes deterministic pretty JSON; `FixedDecimal` preserves Python-like `0.0`
  and `12.3` formatting. Do not replace it with `JSON.stringify`.
- `template.ts` embeds the HTML report exactly.
- Resource comparison covers all APK entries (XML, PNG/WebP, SVG, JSON/text, SQLite DB assets,
  native `.so`, `resources.arsc`, manifest, ...) by size / CRC / SHA-256.
- Reports use LF line endings and are checked against the Python baseline in the CLI test.