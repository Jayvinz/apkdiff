# GitLab CI case

[English](README.md) | [简体中文](README.zh-CN.md)

Shared flow, baseline selection, threshold semantics and the report contract are described in
[`../IMPLEMENTATION.md`](../IMPLEMENTATION.md).

`gitlab/.gitlab-ci.yml` can be copied into the root of an Android repository. For merge requests
targeting `main` it:

1. `build:base` builds the target branch APK;
2. `build:head` builds the merge-request APK;
3. `apk-size` installs apkdiff, compares the APKs, generates reports and enforces the KB
   threshold.

The threshold defaults to **500 KB**; when `apk_size_delta > SIZE_THRESHOLD_KB * 1024` the job
fails, which can block the merge through the project's merge-request settings.

## Files

| File | Description |
| --- | --- |
| `.gitlab-ci.yml` | Complete example with section comments |
| `../../scripts/check-size-threshold.py` | Shared threshold check used by all platforms |

## Quick start

```bash
cp monitor-apk-size-ci/gitlab/.gitlab-ci.yml .gitlab-ci.yml
```

If the project already has a `.gitlab-ci.yml`, copy only the three jobs (`build:base`,
`build:head`, `apk-size`) and the `.android-build` template, then merge them into the existing
`workflow` / `stages` configuration.

Adjust the variables at the top:

```yaml
variables:
  ANDROID_MODULE: "app"
  BUILD_TASK: "assembleRelease"
  SIZE_THRESHOLD_KB: "500"
  APKDIFF_REF: "main"            # pin to a tag / SHA in production
  APKDIFF_REPO: "https://github.com/Jayvinz/apkdiff.git"
  APKDIFF_RAW: "https://raw.githubusercontent.com/Jayvinz/apkdiff"
```

## Runner and image requirements

- **Docker executor**.
- `build:base` / `build:head` need a JDK + Android SDK. The example uses
  `mingc/android-build-box:latest`; replace it with the team's Android build image.
- `apk-size` uses `python:3.12-slim` and installs `git`, `curl` and apkdiff.
- The runner needs access to GitHub (tool installation and threshold-script download). In a
  restricted network, point `APKDIFF_REPO` / `APKDIFF_RAW` at an internal mirror.
- Build jobs time out after 45 minutes; increase this for large projects.

## Choosing the baseline APK

The example uses the **latest target branch commit** as the baseline:

```bash
git fetch origin "+refs/heads/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}:refs/remotes/origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}"
git worktree add --detach base-src "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}"
```

This is simple, but if other commits land on the target branch during the MR, the baseline will
include them. To compare only the patchset's net change relative to its fork point, change the
checkout to:

```bash
base_sha="$(git merge-base HEAD "origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}")"
git worktree add --detach base-src "${base_sha}"
```

Or download the previous release APK and skip `build:base`.

## Threshold

`SIZE_THRESHOLD_KB` is passed to the shared script:

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb "${SIZE_THRESHOLD_KB}" \
  --summary apkdiff-size-report/size-summary.md
```

- Default 500 KB;
- equality passes, only **growth above** the threshold fails;
- a shrinking APK passes;
- `0` rejects any growth.

## Reports and artifacts

The `apk-size` job writes:

```text
apkdiff-size-report/
  apkdiff.json
  apkdiff.html
  apkdiff.md
  size-summary.md
```

and keeps it as a job artifact for 2 weeks (`when: always`, including failures).
`after_script` prints `size-summary.md` to the job log.

## Merge-request gate

In the GitLab project settings:

- Settings → Merge requests → **Pipelines must succeed**; or
- make the pipeline containing `apk-size` a required pipeline.

The merge is blocked when `apk-size` fails, subject to the project's approval / pipeline rules.

## If APKs are produced elsewhere

Remove `build:base` / `build:head` and let upstream jobs provide artifacts:

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

Alternatively, call the shared script with an existing JSON report.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `git worktree` fails | Check `GIT_DEPTH` and that the target branch fetch succeeded |
| APK not found | Check `ANDROID_MODULE`, `BUILD_TASK` and the variant output path |
| Mapping missing | The script creates an empty mapping; reports show obfuscated names |
| apkdiff installation fails | Can the runner reach GitHub? Use an internal PyPI / mirror if not |
| Threshold script download fails | Copy `scripts/check-size-threshold.py` into the project and update `THRESHOLD_SCRIPT` |
| Threshold result looks wrong | Ensure the report path points to `apkdiff.json`, not HTML/Markdown |
