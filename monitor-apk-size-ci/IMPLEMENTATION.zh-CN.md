# APK 体积 CI 实现指南

[English](IMPLEMENTATION.md) | 简体中文

本文说明 `monitor-apk-size-ci` 的通用实现方式和各平台 case 的对应关系。
各平台目录中的配置都遵循同一套流程：

```text
┌─────────────┐     ┌─────────────┐
│ 基线 APK     │     │ PR / patch  │
│ base APK    │     │ head APK    │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 ▼
        apkdiff old.apk new.apk
                 │
                 ▼
  apkdiff.json / apkdiff.html / apkdiff.md
                 │
                 ▼
  check-size-threshold.py
   delta = summary.apk_size_delta
   passed = delta <= threshold_kb * 1024
                 │
        ┌────────┴────────┐
        ▼                 ▼
      PASS              FAIL
  保留报告 artifact   保留报告 + 阻断合并
```

## 1. 输入契约

每个 case 都需要两个 APK：

| 名称 | 含义 | 推荐来源 |
| --- | --- | --- |
| base APK | 变更前的基线 | 目标分支构建、最近一次 release、上一版本 artifact |
| head APK | 本次 PR / patchset 的产物 | CI 构建当前提交 |

mapping 文件可选，但建议提供；没有 mapping 时报告显示混淆类名。

### 基线选择

- **GitHub 示例**：checkout `pull_request.base.sha` 后重新构建。
- **GitLab 示例**：checkout `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` 的目标分支后构建。
- **Gerrit + Jenkins 示例**：`git merge-base HEAD origin/$GERRIT_BRANCH`，避免把目标分支上
  与当前 patchset 无关的提交算进增量。
- 若基线 APK 已经由 release / artifact 提供，可跳过「构建 base」 job，直接把文件路径传给
  后续比较步骤。

## 2. APK 选择

示例假设仓库产物是单个 universal APK：

```text
<module>/build/outputs/apk/**/*.apk
```

如果项目输出 split APK / AAB：

- 对每个需要监控的 APK 分别跑一次比较；或
- 选取 universal APK；
- AAB 需要先通过 bundletool 生成 APK set 再比较。

示例使用 `find ... -name '*.apk' -print -quit` 取第一个 APK，真实项目应按自己的
variant / ABI 策略明确文件路径。

## 3. 阈值语义

阈值单位是 KB，配置项名称为 `threshold-kb` / `SIZE_THRESHOLD_KB`。

```text
threshold_bytes = round(threshold_kb * 1024)
delta_bytes     = summary.apk_size_delta   # 新 APK - 旧 APK
passed          = delta_bytes <= threshold_bytes
```

- 默认 500 KB。
- 恰好等于阈值算通过（只拦截「超过」）。
- 负数（APK 变小）通过。
- `threshold_kb = 0` 表示任何增长都失败。
- 阈值只作用于整体 APK 大小；报告里仍然可以看到类 / 资源级别的明细。

## 4. 共享阈值脚本

`scripts/check-size-threshold.py` 被三个 case 共用：

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb 500 \
  --summary apkdiff-size-report/size-summary.md \
  --github-output "$GITHUB_OUTPUT"   # 可选，仅 GitHub 使用
```

| 参数 | 说明 |
| --- | --- |
| `--report` | apkdiff JSON 报告路径（必填） |
| `--threshold-kb` | 允许的最大增长，默认 500 |
| `--summary` | 额外写出 Markdown 摘要 |
| `--github-output` | 追加 GitHub Actions outputs（可选） |

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 在阈值内（或 APK 变小） |
| 1 | 超过阈值 |
| 2 | 报告缺失 / 解析失败 |

脚本同时会读取 `GITHUB_STEP_SUMMARY`，存在时把摘要写入 GitHub job summary；
GitLab / Jenkins 只使用 `--summary` 和退出码。

## 5. 工具安装

所有 case 都从同一个 GitHub 仓库安装 apkdiff，不依赖包是否已经发布：

```bash
python -m pip install "git+https://github.com/Jayvinz/apkdiff.git@${APKDIFF_REF}#subdirectory=py/packages/core"
python -m pip install --no-deps "git+https://github.com/Jayvinz/apkdiff.git@${APKDIFF_REF}#subdirectory=py/packages/cli"
```

- `APKDIFF_REF` 建议固定到 tag 或 commit SHA，不要长期依赖 `main`。
- GitHub action 支持 `tool-path` 使用本地 checkout，本仓库自测就使用该模式。
- 等 PyPI 发布后，可以替换为固定版本：

  ```bash
  python -m pip install "apkdiff==1.0.0"
  ```

## 6. 报告与 artifact

每次比较生成：

```text
apkdiff-size-report/
  apkdiff.json       # 机器可读，阈值脚本读取它
  apkdiff.html       # 自包含 HTML 报告
  apkdiff.md         # Markdown 表格
  size-summary.md    # 本次门禁摘要：大小、增量、阈值、PASS/FAIL
```

三个平台都把报告目录作为 artifact 保留，即使阈值失败也要保留，方便排查。

## 7. 平台参数映射

| 概念 | GitHub Actions | GitLab CI | Jenkins |
| --- | --- | --- | --- |
| 基线 APK | `old-apk` 输入 | `artifacts/base/base.apk` | `artifacts/base.apk` |
| PR APK | `new-apk` 输入 | `artifacts/head/head.apk` | `artifacts/head.apk` |
| 阈值 | `threshold-kb` 输入 / `SIZE_THRESHOLD_KB` env | `SIZE_THRESHOLD_KB` variable | `SIZE_THRESHOLD_KB` parameter |
| 工具版本 | `tool-ref` | `APKDIFF_REF` | `APKDIFF_REF` |
| 报告 artifact | `actions/upload-artifact` | `artifacts:paths` | `archiveArtifacts` |
| 失败表现 | job fail | job fail | pipeline FAILURE + Gerrit review |

## 8. 安全与权限

- 只读取 APK 和 mapping，不需要上传 APK 到外部服务。
- GitHub：默认 `contents: read` 即可；来自 fork 的 PR 使用只读 token。
- GitLab：runner 需要能访问项目仓库和 GitHub（安装 apkdiff / 下载脚本）。
- Jenkins：需要 Gerrit Trigger 配置的 SSH 凭据和 Python/Android 构建环境；
  Gerrit `Verified` 标签需要对应权限。
- APK 可能包含敏感信息；artifact 保留时间建议按团队策略设置（示例为 1–2 周）。

## 9. 排查

| 现象 | 排查 |
| --- | --- |
| delta 与预期不符 | 确认 base APK 是否来自正确的分支 / merge-base |
| 找不到 APK | 检查 variant、产物路径、`assemble` 任务 |
| mapping 不生效 | 确认 R8 mapping 产物路径，或留空 |
| 报告显示类名为 `a.b` | 没有提供 mapping，或 mapping 与 APK 不匹配 |
| GitLab 构建 job 失败 | runner 是否有 Android SDK / Gradle 缓存 |
| Jenkins 找不到 Gerrit 变量 | 检查 Gerrit Trigger 事件和 SCM refspec |
| 阈值判断为 0 | 检查 report 路径是否指向 `apkdiff.json`，而不是 HTML/MD |

## 10. 扩展新平台

新增 case 时保持以下契约即可：

1. 产出两个 APK 路径和可选 mapping；
2. 安装 apkdiff（固定 ref）；
3. 调用 `apkdiff` 生成 JSON / HTML / Markdown；
4. 调用 `scripts/check-size-threshold.py`，传入 `--threshold-kb` 和 `--summary`；
5. 在失败时阻断合并，并保留报告 artifact。