# apkdiff Java 实现

[English](README.md) | 简体中文

纯 Java 11 实现的 apkdiff，分为两个 Gradle 模块：

| 模块 | 产物 | 用途 |
| --- | --- | --- |
| `apkdiff-core` | `top.jayvin.apkdiff:apkdiff-core` | Maven 库，无运行时依赖 |
| `apkdiff-cli` | `apkdiff-cli-<version>-all.jar` | 独立可执行 jar |

库字节码目标 **Java 11**；构建使用 JDK 17 和 `options.release = 11`。报告与 Python、Node.js
实现逐字节一致。

## 构建

```bash
cd java
./gradlew build
```

产物：

- `apkdiff-core/build/libs/apkdiff-core-<version>.jar`
- `apkdiff-cli/build/libs/apkdiff-cli-<version>-all.jar`

`-sources.jar` 和 `-javadoc.jar` 由发布插件在 `publishToMavenLocal` / Maven Central 发布时生成，
`build` 不会产出。

`-all.jar` 打入库代码和资源，但**不内置 JRE**；需要 Java 11+ 运行。

## 命令行

```bash
java -jar apkdiff-cli/build/libs/apkdiff-cli-1.0.0-alpha01-all.jar \
  old.apk new.apk --detect-renames \
  --format console,json,html,markdown -o report/
```

参数与 Python CLI 一致（`--format`、`--output`、`--metric`、`--top`、`--full`、
`--include-meta`、`--detect-renames`、`--fail-on-regression`）。

控制台输出为 UTF-8。旧版 Windows 控制台如乱码，先执行 `chcp 65001`。

## Maven 依赖

```groovy
dependencies {
    implementation("top.jayvin.apkdiff:apkdiff-core:1.0.0-alpha01")
}
```

POM 无依赖；库以 `--release 11` 编译，可被 Java 11 / 17 / 21 工程消费。

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

公开 API：

- `ApkDiff`：静态门面（`analyze` / `diff` / `mapping` / `printReport` / `write*Report` /
  `size` / `sizeDelta`）
- `ApkAnalyzer.analyze(path, mapping, hashContent)` → `ApkAnalysis`
- `Differ.diff(old, new, includeMeta, detectRenames)` → `DiffResult`
- `Mapping.parse(...)` / `Mapping.load(path)`
- `Reporter.printConsole` / `buildJson` / `writeJson` / `writeHtml` / `writeMarkdown`
- `Util.humanSize` / `humanDelta`

## 测试

```bash
cd java
./gradlew test
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest'
./gradlew :apkdiff-core:test --tests 'top.jayvin.apkdiff.SmallFixtureTest.classChanges'
```

共 21 个测试（core 16 + CLI 5）。fixture 位于 `java/tests/fixtures`，从 Python 生成源复制而来。

## 发布

发布 CI 在设置 `SIGNING_KEY` 后运行 `./gradlew :apkdiff-core:publish`，把签名产物写入
`java/local-repo`，再打包并通过 Central Portal 的 publisher API 上传到 Maven Central；同时把
独立的 `apkdiff-cli-*-all.jar` 作为 GitHub Release 附件。推送 `java-v<version>` tag 只发布
Java，推送 `v<version>` tag 则同时发布三种实现。版本取自 tag，CI 以
`-PapkdiffVersion=<version>` 覆盖 `java/gradle.properties`。

需要在仓库中配置这些 secret：`SONATYPE_USERNAME`、`SONATYPE_PASSWORD`
（Central Portal 的 publishing token）、`SIGNING_KEY`（ASCII-armored 签名私钥）和
`SIGNING_PASSWORD`（私钥无口令时可留空）。

本地只安装、不发布时：

```bash
cd java
./gradlew :apkdiff-core:publishToMavenLocal
```

产物写入 `~/.m2/repository`。本地直接运行 `publish` 只会把未签名产物写入 `java/local-repo`，
只有发布工作流会打包并上传。

## 目录结构

```text
settings.gradle / build.gradle / gradle.properties
gradle/wrapper/
apkdiff-core/
  src/main/java/top/jayvin/apkdiff/
    DexFile.java / ApkAnalyzer.java / Differ.java / Reporter.java
    Mapping.java / Util.java / ApkDiff.java
  src/main/resources/top/jayvin/apkdiff/report-template.html
  src/test/java/...            # 16 个测试
apkdiff-cli/
  src/main/java/top/jayvin/apkdiff/cli/Main.java
  src/test/java/...            # 5 个测试
tests/fixtures/                # fixture 副本
```

## 实现说明

- `DexFile` 把 DEX 字节归属到类；共享池归给按 descriptor 排序的第一个引用者。
  `所有类字节 + unattributed == dex 大小`。
- 类变更比较语义指纹，而不是 dex 原始字节。
- `Reporter` 使用内嵌 HTML 模板和确定性 JSON writer。
- 资源对比覆盖所有 APK zip 条目（XML、PNG/WebP、SVG、JSON/文本、SQLite DB assets、
  native `.so`、`resources.arsc`、manifest 等），按大小 / CRC / SHA-256 对比。
- 报告使用 LF 换行，并通过 CLI 测试与 Python 基线做逐字节比对。