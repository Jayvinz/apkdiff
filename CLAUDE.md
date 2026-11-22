# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

`apkdiff` compares two APKs, attributes DEX bytes to individual classes, compares classes and
resources, and renders console / JSON / HTML / Markdown reports. It contains **three independent
implementations of the same tool**:

- `py/` — Python 3.7+; two PyPI packages: `apkdiff-core` (import `apkdiff_core`) and `apkdiff` (CLI).
- `java/` — pure Java 11; Maven library `top.jayvin.apkdiff:apkdiff-core` and a standalone CLI jar.
- `js/` — Node.js 18+; npm packages `@jayvinz/apkdiff-core` and `@jayvinz/apkdiff-cli`.

All three are intended to produce **byte-identical reports** for the same APK pair. The
`monitor-apk-size-ci/` directory contains CI integrations (GitHub Actions, GitLab CI,
Gerrit + Jenkins) that consume the tool.

## Documentation and comments language

- **Source comments and docstrings are English-first**: Python comment/docstring text, Javadoc,
  TSDoc/JSDoc, YAML comments and Jenkinsfile comments. Do not add new Chinese comments.
- **User-facing documentation is English-first**: `README.md`, `IMPLEMENTATION.md`, case READMEs,
  package READMEs and fixture docs.
- **Every user-facing document must also have a Simplified Chinese counterpart** named
  `<name>.zh-CN.md` (for example `README.zh-CN.md`, `IMPLEMENTATION.zh-CN.md`). Both versions
  link to each other at the top (`English | 简体中文`) and must stay in sync: commands, paths,
  thresholds and option names are identical in both.
- `CLAUDE.md` is agent-facing and English-only; it does not need a Chinese counterpart.
- Commit messages are English as well; keep the repository history clean and avoid mixing
  Chinese-only descriptions into commits.
- **Report/CLI display strings are part of the cross-language output contract** and are currently
  Chinese. Do not translate them in one implementation in isolation; changing them requires
  updating all three implementations and the canonical fixture reports together.

## Commands

### Python

```bash
cd py
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e packages/core -e packages/cli

python -m unittest discover -s tests -v
python -m unittest tests.test_apkdiff.TestDiff.test_class_changes -v   # single test

python -m apkdiff old.apk new.apk --detect-renames \
  --format console,json,html,markdown -o report/

python -m build packages/core      # requires the `build` package
python -m build packages/cli
```

Tests import the installed `apkdiff_core` / `apkdiff` packages. Without installing, set
`PYTHONPATH=packages/core/src:packages/cli/src` (use `;` on Windows).

### Java

```bash
cd java
./gradlew build
./gradlew test
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest'
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest.classChanges'

java -jar apkdiff-cli/build/libs/apkdiff-cli-1.0.0-alpha01-all.jar old.apk new.apk ...
./gradlew :apkdiff-core:publishToMavenLocal  # writes ~/.m2/repository
```

The `--tests` filter must be scoped to a module; an unscoped `./gradlew test --tests ...` fails
because the CLI module has no matching test.

### Node.js

```bash
cd js
npm ci
npm run build
npm test
node --test --test-name-pattern "small fixture: class changes" tests/core.test.cjs   # single test

node packages/cli/dist/cli.js old.apk new.apk --detect-renames
npm pack --workspace @jayvinz/apkdiff-core
npm pack --workspace @jayvinz/apkdiff-cli
```

### CI monitor / threshold script

```bash
python monitor-apk-size-ci/scripts/check-size-threshold.py \
  --report py/report-complex/apkdiff.json \
  --threshold-kb 500 \
  --summary /tmp/size-summary.md
```

The same script is used by GitHub, GitLab and Jenkins. Threshold semantics:
`delta = summary.apk_size_delta`; fail only when `delta > threshold_kb * 1024`.
See `monitor-apk-size-ci/IMPLEMENTATION.md` for the full contract.

## Architecture

### Shared processing pipeline

Each implementation follows the same stages:

1. **ZIP inventory** — enumerate APK entries, record compressed/uncompressed size, CRC and
   SHA-256, classify as `res/`, `assets/`, `lib/`, `META-INF/`, `resources.arsc`,
   `AndroidManifest.xml`, `dex`, or other. This applies to every file type: resource XML
   (layouts/drawables), PNG/WebP, SVG, JSON/text, SQLite `.db` assets, native `.so`, etc.
2. **DEX analysis** — parse every `classes*.dex`:
   - Charge class-specific structures (`class_def`, `class_data`, `code_item`, `debug_info`,
     annotations, static values) to the class.
   - Charge shared pools (`type_ids`, `field_ids`, `method_ids`, `proto_ids`, `string_data`) to
     the **first class in descriptor order** that references them. This deterministic ownership is
     what makes reported class sizes reproducible.
   - Put everything unattributed into `unattributed`; the invariant
     `sum(class sizes) + unattributed == dex file size` is tested.
   - Compute a **semantic fingerprint** from class name, superclass, interfaces, field/method
     signatures, debug local names, annotation types and source file. Do **not** hash raw DEX bytes
     or the first-owner string sets: index pools reshuffle when unrelated classes change.
3. **Diff** — classes compare by semantic fingerprint; resources compare by SHA-256.
   Statuses are `added` / `deleted` / `modified` / `renamed` (renames only with
   `--detect-renames`).
4. **Report** — console, JSON, HTML and Markdown share `Change`/`DiffResult`.

Compressed class size is an estimate: the dex-wide `compress_size / file_size` ratio is applied
to each class's uncompressed attributed bytes.

### Python packages (`py/`)

- `packages/core/src/apkdiff_core/`: `dex.py`, `apk.py`, `mapping.py`, `diff.py`, `report.py`,
  `util.py`; public exports and `__version__` live in `__init__.py`.
- `packages/cli/src/apkdiff/`: CLI only; `__main__.py` enables `python -m apkdiff`.
- Packaging uses setuptools (`>=77` for SPDX `license`), `src` layout, `requires-python >=3.7`.
  Building from sdist needs Python >=3.9 (setuptools 77 requirement); wheels are `py3-none-any`.
  Core version is dynamic from `apkdiff_core.__version__`; the CLI pins `apkdiff-core==1.0.0`.
- Root `LICENSE` (Apache-2.0) covers `py/`, `java/` and `js/`. The two `py/packages/*/LICENSE`
  files are byte-identical copies needed by setuptools (it cannot reference files outside the
  package dir via `license-files`); keep all three in sync.
- Python code must remain 3.7-runtime compatible: `from __future__ import annotations` is used,
  but runtime APIs newer than 3.7 are not. It uses only the standard library.
- `py/report-complex/` holds the canonical example reports (LF endings).

### Java (`java/`)

- `apkdiff-core`: no dependencies; `javac --release 11`/Kotlin-free Java. Main classes mirror the
  Python modules: `DexFile`, `ApkAnalyzer`, `Differ`, `Reporter`, `Mapping`, `ApkDiff` facade.
- `apkdiff-cli`: `Main` plus a `fatJar` task; the `-all.jar` is a standalone executable.
- Gradle build scripts are Groovy DSL. `java/gradle.properties` `apkdiffVersion` is the local
  version; release CI overrides it with `-PapkdiffVersion=<tag version>`. The `apkdiff-core`
  module uses plain `maven-publish` + `signing`: a local `publish` writes unsigned artifacts to
  `java/local-repo`, and release CI bundles that repo and uploads it to Maven Central (Central
  Portal) via the publisher API. `publishToMavenLocal` still writes to `~/.m2/repository`.
- `Reporter` embeds `report-template.html`; JSON is produced by the custom `JsonWriter`, not a
  third-party JSON library.

### Node.js (`js/`)

- npm workspaces: `packages/core` (TypeScript → CommonJS + `.d.ts`) and `packages/cli`
  (`bin` entry `apkdiff`).
- Core has **zero runtime dependencies**. `zip.ts` is a custom ZIP central-directory reader using
  `node:zlib`; `dex.ts` is the DEX parser; `json-writer.ts` writes deterministic pretty JSON.
- `util.ts` `FixedDecimal` preserves Python-like `0.0` / `12.3` formatting in JSON; keep it.
- `template.ts` embeds the HTML report exactly; do not reformat it.
- The CLI supports both `node dist/cli.js` and the installed `apkdiff` bin.

### Releases

`.github/workflows/publish.yml` routes on tag: `py-v*` publishes only PyPI, `java-v*` only
Maven Central, `js-v*` only npm, and a bare `v*` publishes all three. The tag version is stamped
into each module during CI, so checked-in versions may lag behind the latest release. Required
repository secrets: `PYPI_API_TOKEN`, `SONATYPE_USERNAME`, `SONATYPE_PASSWORD`, `SIGNING_KEY`,
`SIGNING_PASSWORD`. `NPM_TOKEN` is optional: an empty value skips only the npm publish step (JS
build/tests still run).

### Fixtures and parity

- The Python fixtures under `py/tests/fixtures/` are the generation source. Copies live in
  `java/tests/fixtures/` and `js/tests/fixtures/` so each language folder is self-contained.
- After regenerating fixtures, re-copy them to both other directories.
- The JS test `cli.test.cjs` compares generated JSON/HTML/Markdown against
  `py/report-complex/` byte-for-byte. When changing report behavior, regenerate canonical reports
  from `py/` and verify all three implementations.

### Monitor CI (`monitor-apk-size-ci/`)

- `scripts/check-size-threshold.py` is shared by all platforms; it writes `size-summary.md`,
  optional GitHub outputs/job summary, and exits 1 when the threshold is exceeded.
- `github/` contains a composite action and a complete PR workflow; `gitlab/` contains
  `.gitlab-ci.yml`; `gerrit-jenkins/` contains a Jenkinsfile and Gerrit Trigger setup docs.
- `.github/workflows/apk-size-monitor-selftest.yml` exercises the GitHub action on this repo's
  fixture APKs. It is a self-test, not an actual Android APK gate.

## Critical invariants

- **Cross-language parity**: a behavior change is not complete until it exists in all three
  implementations and the complex-fixture reports remain byte-identical. Preserve JSON key order,
  number formatting, HTML/Markdown whitespace, and LF line endings.
- The `.gitignore` uses an allowlist (`*` plus explicit `!` entries). New source/config files must
  be explicitly unignored; build outputs, `node_modules`, `dist`, `build`, `local-repo`,
  `*.egg-info`, `__pycache__`, Gradle caches and `.venv` stay ignored.
- Java must stay dependency-free, Java 11 bytecode and Java 11 API compatible (`options.release = 11`).
  Python must stay dependency-free and 3.7+ compatible. JS must stay dependency-free at runtime.
- Release versions come from git tags at CI time (`py-v*`, `java-v*`, `js-v*`, `v*`); the
  checked-in `1.0.0` / `1.0.0-alpha01` values are local defaults only. Git tags/refs used by CI
  should be pinned in production.
- Fixtures are duplicated intentionally; do not edit only one copy.
- Reports use LF on all platforms. Do not use platform-default newline translation.
- The contract for `--metric` is `compressed` by default; `sizeFor`/`oldFor`/`newFor` on `Change`
  centralize metric selection. Keep renderers using those helpers.