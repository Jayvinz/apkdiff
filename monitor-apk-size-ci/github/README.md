# GitHub Actions case

[English](README.md) | [简体中文](README.zh-CN.md)

Shared flow, baseline selection, threshold semantics and the report contract are described in
[`../IMPLEMENTATION.md`](../IMPLEMENTATION.md).

This directory contains:

| File | Purpose |
| --- | --- |
| `action.yml` | Reusable composite action: install apkdiff, compare two APKs, enforce the threshold, upload the report |
| `example-pull-request.yml` | Complete `pull_request → main` example: build base / PR APKs and call the action |
| `../../scripts/check-size-threshold.py` | Shared by all three platforms: read `apkdiff.json`, write summary/outputs, exit 1 when the threshold is exceeded |

## Option 1: copy the complete example

```bash
cp monitor-apk-size-ci/github/example-pull-request.yml \
   .github/workflows/apk-size.yml
```

The example assumes:

- the Android Gradle project is at the repository root;
- the app module is `app` and the build task is `assembleRelease`;
- artifacts are under `app/build/outputs/apk/**/*.apk`;
- the R8 mapping is at `app/build/outputs/mapping/release/mapping.txt` (an empty file is created
  when it is absent).

Adjust the top of `.github/workflows/apk-size.yml`:

```yaml
env:
  ANDROID_MODULE: app
  BUILD_TASK: assembleRelease
  SIZE_THRESHOLD_KB: 500
  APKDIFF_TOOL_REF: main
```

### Obtaining the baseline APK

The example rebuilds the PR base SHA, which is straightforward but adds one build. Alternatives:

- download the latest `main` APK artifact;
- download a fixed baseline APK from GitHub Releases or object storage;
- cache a baseline APK keyed by `base.sha`.

As long as both APK files exist in the workspace, the action can compare them.

## Option 2: call the action from an existing workflow

If base / head APKs are already built or downloaded:

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

Pin `@main` to a release tag or commit SHA to avoid behavior changes from tool updates.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `old-apk` | required | Baseline APK path |
| `new-apk` | required | PR APK path |
| `old-mapping` | empty | Baseline mapping.txt (optional) |
| `new-mapping` | empty | PR mapping.txt (optional) |
| `threshold-kb` | `500` | Maximum allowed growth in KB |
| `metric` | `compressed` | `compressed` or `uncompressed` |
| `detect-renames` | `true` | Detect resources renamed with identical content |
| `output-dir` | `apkdiff-size-report` | Report output directory |
| `artifact-name` | `apk-size-report` | Uploaded artifact name |
| `tool-path` | empty | Local apkdiff checkout; this repository's self-test passes `.` |
| `tool-ref` | `main` | Ref used to install `Jayvinz/apkdiff` when `tool-path` is empty |
| `python-version` | `3.12` | Python used to install / run apkdiff |

## Outputs

| Output | Description |
| --- | --- |
| `delta-bytes` | APK delta in bytes (signed) |
| `delta-kb` | APK delta in KB (2 decimals) |
| `threshold-bytes` | Threshold in bytes |
| `passed` | `true` / `false` |
| `report-dir` | Report directory |

## Report contents

The action writes under `output-dir`:

```text
apkdiff.json
apkdiff.html
apkdiff.md
size-summary.md
```

and uploads it as an artifact. `size-summary.md` is also appended to the GitHub Actions job
summary with base/PR sizes, delta, threshold and the PASS/FAIL result.

## Tool installation

- By default, pip installs this repository's `py/packages/core` and `py/packages/cli` directly
  from GitHub, so it does not require the packages to be published on PyPI.
- This repository's self-test passes `tool-path: .` to use the current checkout.
- If the tool repository is private, ensure the runner has read access, or use an internal
  PyPI / npm mirror.
- Once `apkdiff` / `apkdiff-core` are on PyPI, the install step can use a pinned version:

  ```bash
  pip install "apkdiff==1.0.0a1"
  ```

## Notes

- The example assumes a single universal APK. For split APKs / AABs, select the APK to monitor or
  call the action once per APK.
- The threshold uses the whole APK file size, not code-only or resources-only.
- For fork PRs, the `pull_request` workflow uses a read-only token. This action does not write PR
  comments; it only uploads artifacts and writes the job summary, so no extra permissions are
  required.
- `.github/workflows/apk-size-monitor-selftest.yml` in this repository is a self-test, not a real
  Android size gate.
