# apkdiff Java implementation

[English](README.md) | [简体中文](README.zh-CN.md)

Pure Java 11 implementation of apkdiff, split into two Gradle modules:

| Module | Artifact | Purpose |
| --- | --- | --- |
| `apkdiff-core` | `top.jayvin.apkdiff:apkdiff-core` | Library for Maven consumers; no runtime dependencies |
| `apkdiff-cli` | `apkdiff-cli-<version>-all.jar` | Standalone executable jar |

The library bytecode targets **Java 11**; the build itself uses JDK 17 and
`options.release = 11`. Reports are byte-identical to the Python and Node.js implementations.

## Build

```bash
cd java
./gradlew build
```

Artifacts:

- `apkdiff-core/build/libs/apkdiff-core-<version>.jar`
- `apkdiff-cli/build/libs/apkdiff-cli-<version>-all.jar`

The `-sources.jar` and `-javadoc.jar` are produced by the publishing plugin during
`publishToMavenLocal` / Maven Central publishing, not by `build`.

The `-all.jar` contains the code and resources, but **no JRE**. Run it with Java 11+.

## CLI

```bash
java -jar apkdiff-cli/build/libs/apkdiff-cli-1.0.0-alpha01-all.jar \
  old.apk new.apk --detect-renames \
  --format console,json,html,markdown -o report/
```

Options match the Python CLI (`--format`, `--output`, `--metric`, `--top`, `--full`,
`--include-meta`, `--detect-renames`, `--fail-on-regression`).

Console output is UTF-8. On legacy Windows consoles, run `chcp 65001` first.

## Maven dependency

```groovy
dependencies {
    implementation("top.jayvin.apkdiff:apkdiff-core:1.0.0-alpha01")
}
```

The POM has no dependencies. The library is compiled with `--release 11`, so it can be consumed
by Java 11, 17 and 21 projects.

## Java API

```java
import top.jayvin.apkdiff.*;

Mapping oldMapping = ApkDiff.mapping("old/mapping.txt");
Mapping newMapping = ApkDiff.mapping("new/mapping.txt");
ApkAnalysis oldApk = ApkDiff.analyze("old.apk", oldMapping);
ApkAnalysis newApk = ApkDiff.analyze("new.apk", newMapping);

DiffResult result = ApkDiff.diff(oldApk, newApk, false, true);
ApkDiff.printReport(result, "compressed", 30, false);
ApkDiff.writeJsonReport(result, "report/apkdiff.json", "compressed");
ApkDiff.writeHtmlReport(result, "report/apkdiff.html", "compressed");
ApkDiff.writeMarkdownReport(result, "report/apkdiff.md", "compressed");
```

Public API:

- `ApkDiff`: static facade (`analyze` / `diff` / `mapping` / `printReport` / `write*Report` /
  `size` / `sizeDelta`)
- `ApkAnalyzer.analyze(path, mapping, hashContent)` → `ApkAnalysis`
- `Differ.diff(old, new, includeMeta, detectRenames)` → `DiffResult`
- `Mapping.parse(...)` / `Mapping.load(path)`
- `Reporter.printConsole` / `buildJson` / `writeJson` / `writeHtml` / `writeMarkdown`
- `Util.humanSize` / `humanDelta`

## Tests

```bash
cd java
./gradlew test
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest'
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest.classChanges'
```

21 tests (16 core + 5 CLI). Fixtures are in `java/tests/fixtures` and are copied from the Python
generation source.

## Publishing

Release CI runs `./gradlew :apkdiff-core:publish` with `SIGNING_KEY` set, which writes signed
artifacts to `java/local-repo`, bundles them, and uploads the bundle to Maven Central (Central
Portal) through the publisher API. It also attaches the standalone `apkdiff-cli-*-all.jar` to the
GitHub Release. Push a `java-v<version>` tag to publish Java only, or a bare `v<version>` tag to
publish all three implementations. The tag supplies the version; CI passes it as
`-PapkdiffVersion=<version>` and overrides `java/gradle.properties`.

Required repository secrets: `SONATYPE_USERNAME`, `SONATYPE_PASSWORD` (Central Portal publishing
token), `SIGNING_KEY` (ASCII-armored signing key) and `SIGNING_PASSWORD` (optional for an
unencrypted key).

For a local install without publishing anywhere:

```bash
cd java
./gradlew :apkdiff-core:publishToMavenLocal
```

This writes to `~/.m2/repository`. Plain `publish` writes unsigned artifacts to `java/local-repo`;
only the release workflow bundles and uploads them.

## Layout

```text
settings.gradle / build.gradle / gradle.properties
gradle/wrapper/
apkdiff-core/
  src/main/java/top/jayvin/apkdiff/
    DexFile.java / ApkAnalyzer.java / Differ.java / Reporter.java
    Mapping.java / Util.java / ApkDiff.java
  src/main/resources/top/jayvin/apkdiff/report-template.html
  src/test/java/...            # 16 tests
apkdiff-cli/
  src/main/java/top/jayvin/apkdiff/cli/Main.java
  src/test/java/...            # 5 tests
tests/fixtures/                # fixture copy
```

## Implementation notes

- `DexFile` attributes DEX bytes to classes; shared pools go to the first referencing class
  (descriptor order). `sum(class bytes) + unattributed == dex size`.
- Class changes compare semantic fingerprints, not raw dex bytes.
- `Reporter` uses an embedded HTML template and a deterministic JSON writer.
- Resource comparison covers all APK zip entries (XML, PNG/WebP, SVG, JSON/text, SQLite DB assets,
  native `.so`, `resources.arsc`, manifest, ...) by size / CRC / SHA-256.
- Reports use LF line endings and are checked against the Python baseline through the CLI tests.