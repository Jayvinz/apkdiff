# GitHub Actions case

[English](README.md) | 简体中文

通用流程、基线选择、阈值语义与报告契约见 [`../IMPLEMENTATION.zh-CN.md`](../IMPLEMENTATION.zh-CN.md)。
本目录包含：

| 文件 | 用途 |
| --- | --- |
| `action.yml` | 可复用 composite action：安装 apkdiff、比较两个 APK、执行阈值门禁、上传报告 |
| `example-pull-request.yml` | 完整的 `pull_request → main` 示例：分别构建 base / PR APK 后调用 action |
| `../../scripts/check-size-threshold.py` | 三平台共用：读取 `apkdiff.json`，写 summary / outputs，并在超阈值时返回 1 |

## 方式一：复制完整示例

```bash
cp monitor-apk-size-ci/github/example-pull-request.yml \
   .github/workflows/apk-size.yml
```

示例假设：

- Android Gradle 工程在仓库根目录；
- 应用模块是 `app`，构建任务是 `assembleRelease`；
- 产物位于 `app/build/outputs/apk/**/*.apk`；
- R8 mapping 位于 `app/build/outputs/mapping/release/mapping.txt`（没有时创建空文件）。

按需修改 `.github/workflows/apk-size.yml` 顶部的：

```yaml
env:
  ANDROID_MODULE: app
  BUILD_TASK: assembleRelease
  SIZE_THRESHOLD_KB: 500
  APKDIFF_TOOL_REF: main
```

### 基线 APK 的获取方式

示例采用「在 CI 中从 PR base SHA 重新构建」的方式，最直观但会多花一次构建时间。
实际项目可以换成：

- 下载最近一次 `main` 的 APK artifact；
- 从 GitHub Release / 对象存储下载固定基线包；
- 缓存 baseline APK，按 `base.sha` 命中。

只要最终在 workspace 中有两个 APK 文件，就可以调用 action。

## 方式二：在已有 workflow 中直接调用 action

如果 base / head APK 已经由其他 job 构建或下载好：

```yaml
- name: APK size gate
  id: apk-size
  uses: Jayvinz/apkdiff/monitor-apk-size-ci/github@main
  with:
    old-apk: baseline/app-release.apk
    new-apk: pr/app-release.apk
    old-mapping: baseline/mapping.txt
    new-mapping: pr/mapping.txt
    threshold-kb: 500
```

建议把 `@main` 固定为 release tag 或 commit SHA，避免工具升级导致行为漂移。

## Inputs

| Input | 默认值 | 说明 |
| --- | --- | --- |
| `old-apk` | 必填 | 基线 APK 路径 |
| `new-apk` | 必填 | PR APK 路径 |
| `old-mapping` | 空 | 基线 mapping.txt，可选 |
| `new-mapping` | 空 | PR mapping.txt，可选 |
| `threshold-kb` | `500` | 允许的最大增长，单位 KB |
| `metric` | `compressed` | `compressed` 或 `uncompressed` |
| `detect-renames` | `true` | 是否识别内容相同的资源重命名 |
| `output-dir` | `apkdiff-size-report` | 报告输出目录 |
| `artifact-name` | `apk-size-report` | 上传的 artifact 名称 |
| `tool-path` | 空 | 本地 apkdiff 源码目录；本仓库自测时传 `.` |
| `tool-ref` | `main` | `tool-path` 为空时，从 `Jayvinz/apkdiff` 安装的 ref |
| `python-version` | `3.12` | 安装 / 运行 apkdiff 的 Python 版本 |

## Outputs

| Output | 说明 |
| --- | --- |
| `delta-bytes` | APK 增量（字节，可正可负） |
| `delta-kb` | APK 增量（KB，保留 2 位小数） |
| `threshold-bytes` | 阈值换算成字节 |
| `passed` | `true` / `false` |
| `report-dir` | 报告目录 |

## 报告内容

action 会在 `output-dir` 生成：

```text
apkdiff.json
apkdiff.html
apkdiff.md
size-summary.md
```

并上传为 artifact。`size-summary.md` 同时会写入 GitHub Actions job summary，
包含 base / PR 大小、增量、阈值和 PASS/FAIL 结论。

## 工具安装

- 默认通过 pip 从 GitHub 安装本仓库的 `py/packages/core` 与 `py/packages/cli`，
  不依赖 PyPI 是否已发布。
- 本仓库自测传 `tool-path: .`，直接使用当前 checkout 的代码。
- 如果工具仓库是私有的，需要确保 runner 有读取权限，或改为内部 PyPI / npm 源。
- 等 `apkdiff` / `apkdiff-core` 发布到 PyPI 后，也可以把安装步骤换成固定版本：

  ```bash
  pip install "apkdiff==1.0.0"
  ```

## 注意事项

- 示例假设单个 universal APK。若项目输出 split APK / AAB，需要先选定要监控的 APK，
  或分别对多个 APK 调用 action。
- 阈值按整体 APK 文件大小计算，不是仅代码或仅资源。
- PR 来自 fork 时，`pull_request` workflow 默认使用只读 token；本 action 不写 PR 评论，
  只上传 artifact / 写 job summary，因此无需额外权限。
- 本仓库的 `.github/workflows/apk-size-monitor-selftest.yml` 是自测，不是真实 APK 门禁。
