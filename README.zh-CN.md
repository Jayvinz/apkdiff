# apkdiff

Android APK 包体积 diff 工具。对比两个 APK 版本，把 DEX 字节归属到单个类，逐项对比资源，准确
输出新增、删除、修改、重命名的条目以及每一项带来的体积变化。

[English](README.md) | 简体中文

包体积增长很容易在无意间发布出去，发布后却很难解释清楚。apkdiff 把 APK/Bundle 体积对比放进 PR
流程：同一套比较逻辑在 CI 中运行，生成详细报告，并在 APK 增长超过可配置阈值（默认 **500 KB**）
时让构建失败。

[`monitor-apk-size-ci/`](monitor-apk-size-ci/) 提供可直接使用的 GitHub Actions、GitLab CI 和
Gerrit + Jenkins 接入。本仓库每次向 `main` 提 PR 时，都会用内置 fixture APK 跑一遍 GitHub 接入。

仓库包含三套等价实现：Python、Java 11 和 Node.js，共用同一算法、命令行参数和报告格式。本根
README 使用 Python 举例；各实现的详细文档分别位于 [`py/`](py/)、[`jvm/`](jvm/)、[`js/`](js/)。

## 它到底在干嘛

发版时老板问：“这次包为什么大了 700 KB？”打开 APK 只能看到几千个文件，看不出哪个类、哪张图变大。

1. **拆包**：把两个 APK 当 zip 打开，清点所有条目（资源、so、清单等），并找出所有 `classes*.dex`。
2. **按类记账**：类专属结构直接算给该类；共享表按固定顺序归给“第一个引用它的类”。所有类字节 +
   `unattributed` 等于 dex 大小。
3. **对比**：把新旧清单放一起，标出新增 / 删除 / 修改 / 重命名，并计算体积差。
4. **出报告**：控制台表格，或 HTML / Markdown / JSON 报告。

提供 ProGuard/R8 `mapping.txt` 时会把混淆类名还原成业务类名。变更判定使用语义指纹，而不是 dex
原始字节，避免索引池重排导致大面积误报。

## PR CI 中的持续 APK/Bundle 体积监控

这个工具不只用于一次性排查。[`monitor-apk-size-ci/`](monitor-apk-size-ci/) 中的接入会对比基线
APK 与 PR / patchset 产出的 APK，生成 `apkdiff.json` / `apkdiff.html` / `apkdiff.md` 以及
`size-summary.md`，并在 `summary.apk_size_delta` 超过阈值（默认 **500 KB**）时让任务失败：

- GitHub Actions：composite action + 完整 PR 工作流；
- GitLab CI：merge request 流水线；
- Gerrit + Jenkins：patchset 流水线 + `Verified` 投票。

三种接入共用
[`scripts/check-size-threshold.py`](monitor-apk-size-ci/scripts/check-size-threshold.py) 的阈值
逻辑，完整约定见
[`monitor-apk-size-ci/IMPLEMENTATION.zh-CN.md`](monitor-apk-size-ci/IMPLEMENTATION.zh-CN.md)。

监控对象是 APK 产物。项目若发布 Android App Bundle，可先用 `bundletool` 生成 APK set，再选定
要监控的 APK；split APK 同理。

本仓库使用
[`.github/workflows/apk-size-monitor-selftest.yml`](.github/workflows/apk-size-monitor-selftest.yml)
中的 GitHub 接入：每次 PR 到 `main` 都会对比内置复杂 fixture APK，并执行 500 KB 门禁。

## Python 快速开始

要求 Python 3.7 – 3.14，仅使用标准库。

```bash
pip install apkdiff
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt \
  --new-mapping new/mapping.txt \
  --format console,json,html,markdown \
  -o report/
```

不指定 mapping 时，会自动探测 APK 同目录的 `<apk名>-mapping.txt`、`<apk名>.mapping.txt` 或
`mapping.txt`。

作为库使用：

```bash
pip install apkdiff-core
```

```python
from apkdiff_core import analyze_apk, diff_apks, load_mapping, write_json

old = analyze_apk("old.apk", load_mapping("old/mapping.txt"))
new = analyze_apk("new.apk", load_mapping("new/mapping.txt"))
result = diff_apks(old, new, detect_renames=True)
write_json(result, "report/apkdiff.json", "compressed")
```

本地开发、构建 wheel、发布 PyPI 见 [`py/README.zh-CN.md`](py/README.zh-CN.md)。

## 通用命令行参数

三套实现参数一致：

| 参数 | 说明 |
| --- | --- |
| `--format` | `console,json,html,markdown`，默认 `console,json,html` |
| `-o, --output` | 报告目录，默认 `apkdiff-report` |
| `--metric` | `compressed`（默认）或 `uncompressed` |
| `--top N` | 控制台每种类型显示条数，默认 30 |
| `--full` | 控制台显示全部条目 |
| `--include-meta` | 把 `META-INF/` 纳入资源对比（默认排除） |
| `--detect-renames` | 把内容相同的删除 + 新增识别为重命名 |
| `--fail-on-regression` | 新 APK 变大时退出码 1（CI 门禁） |

## 输出

- 控制台：APK / 代码 / 资源总览、变更统计、按影响排序的类与资源明细。
- `apkdiff.json`：完整结构化数据，含 `delta`、`compressed_delta`、哈希和明细。
- `apkdiff.html`：自包含报告，支持搜索、状态过滤和排序。
- `apkdiff.md`：Markdown 表格。

## 体积口径

### 类

解析所有 `classes*.dex`。类专属结构（`class_def`、`class_data`、`code`、`debug_info`、注解、
静态值）直接计入该类；共享表（`type_ids`、`field_ids`、`method_ids`、`proto_ids`、
`string_data`、type list）按固定顺序归给第一个引用者；剩余部分计入 `unattributed`，满足：

```text
所有类字节 + unattributed = dex 文件大小
```

每个 dex 的压缩贡献按整体压缩率 `compress_size / file_size` 估算到类上。

变更判定使用语义指纹（类名、父类、接口、字段 / 方法签名、调试局部变量名、注解类型、源文件），
不使用 dex 原始字节。新增 / 删除类会导致索引重排，直接比原始字节会误报大量修改。

### 资源

按 APK zip 条目名对比，记录压缩 / 未压缩大小、CRC、SHA-256。覆盖所有条目类型：资源 XML、
PNG/WebP、SVG、JSON/HTML/文本、SQLite `.db` assets、native `.so`、`resources.arsc`、
`AndroidManifest.xml` 等。

- 新增：只在新 APK
- 删除：只在旧 APK
- 修改：两边都有但内容哈希不同
- 重命名：`--detect-renames` 下，删除项与新增项内容哈希相同

`META-INF/` 默认排除，`--include-meta` 可纳入。

## 测试与 fixtures

两套 fixture 使用真实 Android 工具链（javac + d8 + aapt）生成：

1. **小型 fixture**：3 个类，快速冒烟。
2. **复杂 fixture**：模拟电商 App，214 → 225 个业务类，3 个 dex，80+ 资源（XML、PNG、SVG、
   JSON、SQLite DB、native 库），受控增删改及资源重命名。详见
   [`py/tests/COMPLEX_FIXTURE.zh-CN.md`](py/tests/COMPLEX_FIXTURE.zh-CN.md)。

fixture 在 `py/tests/fixtures`、`jvm/tests/fixtures`、`js/tests/fixtures` 各有一份；Python
目录是生成源，重新生成后同步到另外两份。

```bash
# Python（15 个用例；先按 py/README.zh-CN.md 安装两个本地包）
cd py && python -m unittest discover -s tests -v
```

JVM 与 Node.js 的测试命令见各自目录下的 README。

## 目录结构

```text
py/          Python 实现及详细文档
jvm/         Java 11 实现及详细文档
js/          Node.js 实现及详细文档
monitor-apk-size-ci/   GitHub / GitLab / Gerrit+Jenkins 体积门禁接入
每个实现目录下的 tests/fixtures 保持同步
```

## 已知限制

- 只统计 dex 内类，不解析 Kotlin metadata / Compose 编译器生成物的额外语义。
- 资源按条目名对比；`resources.arsc` 中资源 ID 重排不展开到每个资源项。
- 未做 R8 全量符号还原，仅类级反混淆。
- 未解析 native `.so` 的符号级体积。