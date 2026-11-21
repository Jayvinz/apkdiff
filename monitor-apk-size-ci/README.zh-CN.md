# monitor-apk-size-ci

[English](README.md) | 简体中文

APK 体积 CI 监控接入示例。目标是在代码评审阶段对比「基线 APK」和「本次变更构建的 APK」，
生成 apkdiff 报告，并在增量超过阈值时让检查失败。

当前包含三个 case：

| 平台 | 目录 | 形态 |
| --- | --- | --- |
| GitHub Actions | [`github/`](github/) | 可复用 composite action + PR 工作流示例 |
| GitLab CI | [`gitlab/`](gitlab/) | `.gitlab-ci.yml` 示例 |
| Gerrit + Jenkins | [`gerrit-jenkins/`](gerrit-jenkins/) | Declarative `Jenkinsfile` + Gerrit Trigger 配置说明 |

公共实现细节、基线选择、阈值语义、报告结构和平台参数映射见
[`IMPLEMENTATION.zh-CN.md`](IMPLEMENTATION.zh-CN.md)。阈值判定逻辑由三平台共用：

```text
scripts/check-size-threshold.py
```

## 判定口径

- 增量取自 apkdiff JSON 报告的 `summary.apk_size_delta`，即两个 APK 文件大小之差（压缩后）。
- `threshold-kb` 默认 `500`，即允许变更后的 APK 最多比基线大 500 KB。
- 只有 **增长超过** 阈值才失败；`delta <= threshold` 通过，APK 变小也通过。
- 阈值设为 `0` 时，任何体积增长都会失败，适合严格门禁。
- 报告包含 `apkdiff.json` / `apkdiff.html` / `apkdiff.md` / `size-summary.md`，
  并在各平台作为 artifact 保留；失败时也保留。

## GitHub Actions

复制 [`github/example-pull-request.yml`](github/example-pull-request.yml) 到业务仓库的
`.github/workflows/apk-size.yml`，按项目修改：

```yaml
env:
  ANDROID_MODULE: app
  BUILD_TASK: assembleRelease
  SIZE_THRESHOLD_KB: 500
  APKDIFF_TOOL_REF: main
```

工作流在 PR 目标为 `main` 时构建 base/head APK，调用
[`github/action.yml`](github/action.yml)，生成报告并执行阈值门禁。
详细输入/输出见 [`github/README.zh-CN.md`](github/README.zh-CN.md)。

## GitLab CI

复制 [`gitlab/.gitlab-ci.yml`](gitlab/.gitlab-ci.yml) 到业务仓库根目录：

```bash
cp monitor-apk-size-ci/gitlab/.gitlab-ci.yml .gitlab-ci.yml
```

工作流在 MR 目标为 `main` 时：

1. `build:base` 构建目标分支 APK；
2. `build:head` 构建 MR APK；
3. `apk-size` 安装 apkdiff、比较、生成报告、执行 `SIZE_THRESHOLD_KB` 门禁。

Runner、镜像、基线与 artifact 说明见 [`gitlab/README.zh-CN.md`](gitlab/README.zh-CN.md)。

## Gerrit + Jenkins

把 [`gerrit-jenkins/Jenkinsfile`](gerrit-jenkins/Jenkinsfile) 放入 Gerrit 项目，
配置 Gerrit Trigger 监听 `Patchset Created`：

- 构建基线：`merge-base(HEAD, target branch)`；
- 构建 patchset APK；
- 安装 apkdiff、生成报告、执行阈值；
- 失败时 pipeline FAILURE，并给 Gerrit patchset 投 `Verified -1`；
- 报告归档，summary 写回 Gerrit review message。

Gerrit server、job trigger、SCM refspec、权限和排查步骤见
[`gerrit-jenkins/README.zh-CN.md`](gerrit-jenkins/README.zh-CN.md)。

## 本仓库自测

`.github/workflows/apk-size-monitor-selftest.yml` 会在本仓库 PR 到 `main` 时，
用 `js/tests/fixtures/complex` 的两份 fixture APK 跑一遍完整监控流程（阈值 500 KB），
用来验证 action 安装、报告生成、阈值判定和 artifact 上传都正常。