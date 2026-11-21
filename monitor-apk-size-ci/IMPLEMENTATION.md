# APK size CI implementation guide

[English](IMPLEMENTATION.md) | [简体中文](IMPLEMENTATION.zh-CN.md)

This document describes the shared implementation used by `monitor-apk-size-ci`. Every platform
case follows the same flow:

```text
┌─────────────┐     ┌─────────────┐
│ baseline APK│     │ PR / patch  │
│ (base APK)  │     │ (head APK)  │
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
  keep report artifact  keep report + block merge
```

## 1. Input contract

Every case needs two APKs:

| Name | Meaning | Recommended source |
| --- | --- | --- |
| base APK | The baseline before the change | target-branch build, latest release, previous artifact |
| head APK | The artifact produced by this PR / patchset | CI build of the current commit |

Mapping files are optional but recommended; without them reports show obfuscated class names.

### Choosing the baseline

- **GitHub example**: check out `pull_request.base.sha` and rebuild.
- **GitLab example**: check out `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` and rebuild.
- **Gerrit + Jenkins example**: use `git merge-base HEAD origin/$GERRIT_BRANCH` so unrelated
  commits merged into the target branch are not counted in the delta.
- If a stable baseline APK already exists (release / artifact store), skip the "build base" job and
  pass its path directly to the comparison step.

## 2. Selecting the APK

The examples assume a single universal APK:

```text
<module>/build/outputs/apk/**/*.apk
```

If the project produces split APKs or AABs:

- run the comparison once per APK that should be monitored, or
- select the universal APK;
- for AABs, generate an APK set with bundletool first.

The examples use `find ... -name '*.apk' -print -quit` to take the first APK. Real projects should
select their variant/ABI artifact explicitly.

## 3. Threshold semantics

The threshold is configured in KB as `threshold-kb` / `SIZE_THRESHOLD_KB`.

```text
threshold_bytes = round(threshold_kb * 1024)
delta_bytes     = summary.apk_size_delta   # new APK - old APK
passed          = delta_bytes <= threshold_bytes
```

- Default: 500 KB.
- Equality passes; only "above" fails.
- A negative delta (APK shrank) passes.
- `threshold_kb = 0` rejects any growth.
- The threshold applies to the whole APK; class/resource details are still available in the report.

## 4. Shared threshold script

`scripts/check-size-threshold.py` is shared by all three cases:

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb 500 \
  --summary apkdiff-size-report/size-summary.md \
  --github-output "$GITHUB_OUTPUT"   # optional, GitHub only
```

| Argument | Description |
| --- | --- |
| `--report` | apkdiff JSON report path (required) |
| `--threshold-kb` | maximum allowed growth; default 500 |
| `--summary` | also write a Markdown summary |
| `--github-output` | append GitHub Actions outputs (optional) |

Exit codes:

| Exit code | Meaning |
| --- | --- |
| 0 | Within the threshold (or the APK shrank) |
| 1 | Threshold exceeded |
| 2 | Report missing / malformed |

The script also appends to `GITHUB_STEP_SUMMARY` when present. GitLab and Jenkins use
`--summary` and the exit code.

## 5. Installing the tool

All cases install apkdiff from the same GitHub repository, independent of whether packages have
been published:

```bash
python -m pip install "git+https://github.com/Jayvinz/apkdiff.git@${APKDIFF_REF}#subdirectory=py/packages/core"
python -m pip install --no-deps "git+https://github.com/Jayvinz/apkdiff.git@${APKDIFF_REF}#subdirectory=py/packages/cli"
```

- Pin `APKDIFF_REF` to a tag or commit SHA in production.
- The GitHub action also supports `tool-path` to use a local checkout; this repository's
  self-test uses that mode.
- Once PyPI packages are published, this can become:

  ```bash
  python -m pip install "apkdiff==1.0.0a1"
  ```

## 6. Reports and artifacts

Each comparison produces:

```text
apkdiff-size-report/
  apkdiff.json       # machine-readable; consumed by the threshold script
  apkdiff.html       # self-contained HTML report
  apkdiff.md         # Markdown tables
  size-summary.md    # gate summary: sizes, delta, threshold, PASS/FAIL
```

All three platforms retain the report directory as an artifact, even when the gate fails.

## 7. Platform parameter mapping

| Concept | GitHub Actions | GitLab CI | Jenkins |
| --- | --- | --- | --- |
| Base APK | `old-apk` input | `artifacts/base/base.apk` | `artifacts/base.apk` |
| PR APK | `new-apk` input | `artifacts/head/head.apk` | `artifacts/head.apk` |
| Threshold | `threshold-kb` input / `SIZE_THRESHOLD_KB` env | `SIZE_THRESHOLD_KB` variable | `SIZE_THRESHOLD_KB` parameter |
| Tool version | `tool-ref` | `APKDIFF_REF` | `APKDIFF_REF` |
| Report artifact | `actions/upload-artifact` | `artifacts:paths` | `archiveArtifacts` |
| Failure | job fails | job fails | pipeline FAILURE + Gerrit review |

## 8. Security and permissions

- Only APKs and mapping files are read; no APK content is uploaded to an external service.
- GitHub: `contents: read` is sufficient; fork PRs use a read-only token.
- GitLab: the runner needs access to the project and to GitHub (tool installation / script
  download).
- Jenkins: requires Gerrit Trigger SSH credentials plus a Python/Android build environment; the
  Gerrit `Verified` label needs the appropriate permission.
- APKs can contain sensitive data; choose artifact retention according to team policy (the
  examples use 1–2 weeks).

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| Delta differs from expectations | Was the base APK built from the correct branch / merge-base? |
| APK not found | Variant, output path, and `assemble` task |
| Mapping not applied | R8 mapping output path; leave it empty if unavailable |
| Class names show as `a.b` | No mapping supplied, or mapping does not match the APK |
| GitLab build job fails | Does the runner have the Android SDK / Gradle cache? |
| Jenkins cannot find Gerrit variables | Gerrit Trigger event and SCM refspec |
| Threshold result looks wrong | Is the report path `apkdiff.json` (not HTML/Markdown)? |

## 10. Adding a new platform

Keep the same contract when adding a case:

1. Produce two APK paths and optional mappings;
2. install apkdiff at a pinned ref;
3. invoke `apkdiff` to generate JSON / HTML / Markdown;
4. invoke `scripts/check-size-threshold.py` with `--threshold-kb` and `--summary`;
5. block the merge on failure and retain the report artifact.
