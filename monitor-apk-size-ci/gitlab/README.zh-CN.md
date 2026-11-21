# GitLab CI case

[English](README.md) | 简体中文

通用流程、基线选择、阈值语义与报告契约见 [`../IMPLEMENTATION.zh-CN.md`](../IMPLEMENTATION.zh-CN.md)。

`gitlab/.gitlab-ci.yml` 是一个可直接复制到 Android 项目根的 GitLab CI 配置。
它在 **merge request 目标分支为 `main`** 时：

1. `build:base`：构建目标分支最新的 APK；
2. `build:head`：构建 merge request 的 APK；
3. `apk-size`：安装 apkdiff，比较两个 APK，生成报告，执行 KB 阈值门禁。

阈值默认 **500 KB**；`apk_size_delta > SIZE_THRESHOLD_KB * 1024` 时 job 失败，
从而可以在 GitLab 的 merge request 设置中阻止合并。

## 文件

| 文件 | 说明 |
| --- | --- |
| `.gitlab-ci.yml` | 完整示例，含逐段注释 |
| `../../scripts/check-size-threshold.py` | 三平台共用的阈值判定脚本 |

## 快速使用

```bash
cp monitor-apk-size-ci/gitlab/.gitlab-ci.yml .gitlab-ci.yml
```

如果项目已有 `.gitlab-ci.yml`，可以只复制三个 job（`build:base`、`build:head`、
`apk-size`）和 `.android-build` 模板，并保留自己的 `workflow` / `stages` 配置。

然后修改文件顶部 `variables`：

```yaml
variables:
  ANDROID_MODULE: "app"
  BUILD_TASK: "assembleRelease"
  SIZE_THRESHOLD_KB: "500"
  APKDIFF_REF: "main"            # 生产环境建议固定到 tag / SHA
  APKDIFF_REPO: "https://github.com/Jayvinz/apkdiff.git"
  APKDIFF_RAW: "https://raw.githubusercontent.com/Jayvinz/apkdiff"
```

## Runner 与镜像要求

- **Docker executor**。
- `build:base` / `build:head` 需要 JDK + Android SDK。示例使用
  `mingc/android-build-box:latest`；如果公司内部有自己的 Android 构建镜像，替换即可。
- `apk-size` 使用 `python:3.12-slim`，脚本会安装 `git`、`curl`、`apkdiff`。
- runner 需要能访问 GitHub（安装 apkdiff、下载阈值脚本）。内网环境可以把
  `APKDIFF_REPO` / `APKDIFF_RAW` 指向内部镜像。
- 构建 job 默认 45 分钟超时；大型项目可在 job 上调大。

## 基线 APK 的选取

示例用 **目标分支最新提交** 作为基线：

```bash
git fetch origin "+refs/heads/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}:refs/remotes/origin/${...}"
git worktree add --detach base-src "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}"
```

这样构建简单，但如果目标分支在 MR 期间又合入了别的提交，基线会包含那些变化。
如果希望只对比「当前 patchset 相对 merge-base 的净增量」，可以把 `base-src` 的
checkout 改为：

```bash
base_sha="$(git merge-base HEAD "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}")"
git worktree add --detach base-src "${base_sha}"
```

也可以直接下载上一版本 release APK，跳过 `build:base`。

## 阈值

`SIZE_THRESHOLD_KB` 由 `apk-size` job 传给共享脚本：

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb "${SIZE_THRESHOLD_KB}" \
  --summary apkdiff-size-report/size-summary.md
```

- 默认 500 KB；
- 等于阈值通过，只有 **超过** 才失败；
- APK 变小通过；
- 设为 `0` 时任何增长都失败。

## 报告与 artifact

`apk-size` job 在 `apkdiff-size-report/` 生成：

```text
apkdiff.json
apkdiff.html
apkdiff.md
size-summary.md
```

并作为 job artifact 保留 2 周（`when: always`，失败也保留）。
`after_script` 会把 `size-summary.md` 打到 job log，方便直接查看结论。

## MR 合并门禁

在 GitLab 项目设置中：

- Settings → Merge requests → **Pipelines must succeed**；
- 或把 `apk-size` job 所在 pipeline 设为 required pipeline。

只要 `apk-size` 失败，MR 就无法合并（具体取决于项目的 approval / pipeline 规则）。

## 如果 APK 已由其他 job 生成

可以删除 `build:base` / `build:head`，让上游 job 通过 `artifacts` 提供：

```yaml
apk-size:
  needs:
    - job: your-build-base
      artifacts: true
    - job: your-build-head
      artifacts: true
  script:
    - apkdiff path/to/base.apk path/to/head.apk ...
```

或者直接调用共享脚本，传入已有的 JSON 报告。

## 排查

| 问题 | 处理 |
| --- | --- |
| `git worktree` 失败 | 确认 `GIT_DEPTH` 足够、目标分支 fetch 成功 |
| 找不到 APK | 检查 `ANDROID_MODULE`、`BUILD_TASK`、variant 产物路径 |
| mapping 缺失 | 脚本会创建空 mapping，报告显示混淆名 |
| 安装 apkdiff 失败 | runner 是否能访问 GitHub；或改用内部 PyPI / mirror |
| 下载阈值脚本失败 | 把 `scripts/check-size-threshold.py` 复制进项目，并修改 `THRESHOLD_SCRIPT` 路径 |
| 阈值判定异常 | 确认报告路径是 `apkdiff.json`，不是 HTML/Markdown |
