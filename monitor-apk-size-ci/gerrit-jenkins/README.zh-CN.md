# Gerrit + Jenkins case

[English](README.md) | 简体中文

通用流程、基线选择、阈值语义与报告契约见 [`../IMPLEMENTATION.zh-CN.md`](../IMPLEMENTATION.zh-CN.md)。

`Jenkinsfile` 是一个完整的 Gerrit patchset 体积门禁流水线：

```text
Gerrit patchset-created
        │
        ▼
Jenkins job (Gerrit Trigger)
        │
        ├─ checkout patchset
        ├─ build baseline from merge-base(HEAD, target branch)
        ├─ build patchset APK
        ├─ apkdiff base.apk head.apk → JSON/HTML/Markdown
        ├─ check-size-threshold.py（默认 500 KB）
        └─ archive report + Gerrit Verified vote / comment
```

阈值默认 **500 KB**；增量超过阈值时流水线 FAILURE，并给 Gerrit patchset 投
`Verified -1`，从而阻止 submit。

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `Jenkinsfile` | Declarative Pipeline，含逐阶段注释 |
| `../../scripts/check-size-threshold.py` | 三平台共用的阈值判定脚本 |

## 1. 前置条件

### Jenkins agent

- 标签为 `android`（可按需修改 `agent { label 'android' }`）。
- JDK + Android SDK，能够执行项目的 Gradle 构建。
- `python3`（3.9+）、`python3-venv`、`curl`、`git`。
- 能访问 GitHub（安装 apkdiff、下载阈值脚本），或改成内部 PyPI / mirror。
- 建议不要开启 SCM 浅克隆，或保证能 fetch 目标分支；流水线会执行
  `git fetch origin refs/heads/<target>` 并计算 `merge-base`。

### Jenkins 插件

- **Gerrit Trigger**：接收 Gerrit 事件并 checkout patchset。
- **Pipeline**（Jenkins 内置）。
- 可选：Timestamper、Workspace Cleanup 等。

### Gerrit 权限

Jenkins 使用的 Gerrit 账号需要：

- 通过 SSH 访问 Gerrit（通常端口 29418）；
- 对目标项目有读取权限；
- 有权限在目标分支上投 `Verified`（以及需要时的 `Code-Review`）；
- 如果使用 `gerritReview` 步骤，需要在 Gerrit Trigger 配置中绑定该账号。

## 2. 配置 Gerrit Trigger

Management Jenkins → **Gerrit Trigger** → **Add New Server**：

| 字段 | 示例 |
| --- | --- |
| Name | `gerrit` |
| Hostname | `gerrit.example.com` |
| SSH Port | `29418` |
| Username | `jenkins` |
| SSH Key | Jenkins 凭据中的私钥 |
| Frontend URL | `https://gerrit.example.com` |

在 Jenkins job 中配置触发条件：

1. 新建 Pipeline job（Pipeline script from SCM），SCM 指向 Gerrit 项目。
2. Git SCM 的 **Refspec** 填：
   ```text
   ${GERRIT_REFSPEC}
   ```
3. **Branch Specifier** 填：
   ```text
   ${GERRIT_PATCHSET_REVISION}
   ```
   或者使用 Gerrit Trigger 文档推荐的 `FETCH_HEAD` 配置。
4. 勾选 **Honor refspec on initial clone**。
5. 在 job 的 **Gerrit Trigger** 区域添加：
   - Project：目标项目，例如 `my/android/app`；
   - Branch：`refs/heads/main`（或 `main`，取决于插件版本/类型）；
   - Event：**Patchset Created**。
6. 保存后 gerrit patchset 会触发一次 build。

Jenkinsfile 中的 `checkout scm` 依赖上述 SCM 配置；如果 job 只有一个内联
Pipeline（没有 SCM），需要把 checkout 改成显式的 `git` step 或
`checkout([$class: 'GitSCM', ...])`。

## 3. Job 参数

Jenkinsfile 顶部定义了：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `SIZE_THRESHOLD_KB` | `500` | 允许的 APK 增长，单位 KB |
| `APKDIFF_REF` | `main` | apkdiff 的 git ref，生产建议固定 tag/SHA |
| `ANDROID_MODULE` | `app` | Gradle 模块 |
| `BUILD_TASK` | `assembleRelease` | Gradle 构建任务 |

可以在 job 配置中保留默认值，也可以由 Gerrit Trigger 或手动 build 覆盖。

## 4. 流水线阶段

1. **Checkout patchset**
   - 打印 `GERRIT_PROJECT`、`GERRIT_BRANCH`、`GERRIT_PATCHSET_NUMBER`、
     `GERRIT_PATCHSET_REVISION`，方便排查。
   - `checkout scm` 使用 Gerrit Trigger / Git SCM 配置。

2. **Build baseline APK**
   - `git fetch origin refs/heads/${GERRIT_BRANCH}`；
   - `git merge-base HEAD origin/${GERRIT_BRANCH}` 得到基线提交；
   - 在 `base-src` worktree 中执行 Gradle；
   - 产物复制到 `artifacts/base.apk`。

3. **Build patchset APK**
   - 在当前 workspace（patchset）执行 Gradle；
   - 产物复制到 `artifacts/head.apk`。

4. **APK size gate**
   - 创建 `.apkdiff-venv`，安装 apkdiff；
   - 下载共享阈值脚本；
   - 生成 `apkdiff-size-report/{apkdiff.json,apkdiff.html,apkdiff.md}`；
   - 运行阈值脚本，记录 PASS/FAIL；
   - 超过阈值通过 `error()` 让 pipeline FAILURE。

5. **post always**
   - `archiveArtifacts` 保留报告；
   - 调用 `gerritReview`：
     - PASS → `Verified +1`；
     - FAIL / 构建失败 → `Verified -1`；
     - message 包含 `size-summary.md` 内容。

## 5. 基线选择

示例使用：

```bash
base_sha="$(git merge-base HEAD "origin/${GERRIT_BRANCH}")"
```

这表示「当前 patchset 相对目标分支分叉点的净增量」，避免把 patchset 创建后
目标分支上合入的其他 commit 算进来。

如果团队希望对比「上一次发布版本」，可以改成下载固定 baseline APK，并删除
`Build baseline APK` 阶段：

```groovy
stage('Download baseline APK') {
  steps {
    sh 'mkdir -p artifacts && curl -fL "$BASELINE_APK_URL" -o artifacts/base.apk'
  }
}
```

## 6. 阈值

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb 500 \
  --summary apkdiff-size-report/size-summary.md
```

- 默认 500 KB；
- `delta <= threshold` 通过；
- 只有 **超过** 才失败；
- APK 变小通过；
- `0` 表示任何增长都失败。

## 7. Gerrit review

Jenkinsfile 使用 Gerrit Trigger 插件提供的 `gerritReview` step：

```groovy
gerritReview(
  labels: [Verified: passed ? 1 : -1],
  message: "APK size gate: ${passed ? 'PASS' : 'FAIL'}\n\n${summary}"
)
```

如果插件版本不支持该 step，或希望完全用 SSH，可以改成：

```bash
vote=1
[ "${SIZE_PASSED}" = "true" ] || vote=-1

ssh -p 29418 jenkins@gerrit.example.com \
  gerrit review \
  --verified "${vote}" \
  --message "APK size gate: ${SIZE_PASSED} (see Jenkins report)" \
  "${GERRIT_PATCHSET_REVISION}"
```

注意：

- `--verified 1/0/-1` 需要账号有对应标签权限；
- message 过长会被 Gerrit 截断，summary 已经控制在较小体积；
- 如果只想评论、不投票，去掉 `labels` 即可。

## 8. 报告 artifact

`apkdiff-size-report/` 会归档：

```text
apkdiff.json
apkdiff.html
apkdiff.md
size-summary.md
```

失败时也会归档。需要保留 APK 本身时，在 `post` 的 `archiveArtifacts` 里追加：

```groovy
artifacts: "apkdiff-size-report/**,artifacts/**"
```

注意 APK 体积较大，按团队保留策略设置。

## 9. 常见问题

| 现象 | 排查 |
| --- | --- |
| Gerrit 事件没有触发 job | Gerrit Trigger server 状态、项目/分支过滤、插件事件配置 |
| `checkout scm` 为空 | job 是否配置了 Git SCM，不是纯内联 Pipeline |
| `GERRIT_BRANCH` 为空 | 手动 build 时没有 Gerrit 环境变量；流水线会回退到 `main` |
| `merge-base` 失败 | 目标分支未 fetch；关闭浅克隆或增加 fetch |
| 找不到 APK | `ANDROID_MODULE` / `BUILD_TASK` / variant 产物路径 |
| Python venv 创建失败 | agent 是否安装 `python3-venv` |
| 安装 apkdiff 失败 | agent 是否能访问 GitHub；改用内部 mirror / PyPI |
| Gerrit 投票失败 | Jenkins Gerrit 账号是否有 `Verified` 权限，插件 server 是否配置 |
| 阈值结果异常 | 确认读取的是 `apkdiff.json`，不是 HTML/Markdown |

## 10. 与其它 case 的差异

- GitHub / GitLab 在 CI 平台内管理 artifact 与失败状态；
- Gerrit + Jenkins 额外把结果写回代码评审（`Verified` 标签 + 评论），
  因此门禁结果直接出现在 patchset 页面。
- 三个 case 共用同一个阈值脚本和相同的 apkdiff 报告格式。
