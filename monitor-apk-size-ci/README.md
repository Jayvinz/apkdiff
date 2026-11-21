# monitor-apk-size-ci

[English](README.md) | [简体中文](README.zh-CN.md)

CI integrations for APK size monitoring. The goal is to compare a baseline APK with the APK built
from a pull request / patchset, generate an apkdiff report, and fail the check when the size
increase exceeds a threshold.

Current cases:

| Platform | Directory | Form |
| --- | --- | --- |
| GitHub Actions | [`github/`](github/) | Reusable composite action + PR workflow example |
| GitLab CI | [`gitlab/`](gitlab/) | `.gitlab-ci.yml` example |
| Gerrit + Jenkins | [`gerrit-jenkins/`](gerrit-jenkins/) | Declarative `Jenkinsfile` + Gerrit Trigger setup |

Shared implementation details, baseline strategies, threshold semantics, report structure and
platform parameter mapping live in [`IMPLEMENTATION.md`](IMPLEMENTATION.md). The threshold check
is shared by all three platforms:

```text
scripts/check-size-threshold.py
```

## Gate semantics

- The delta comes from `summary.apk_size_delta` in the apkdiff JSON report: new APK size minus
  baseline APK size (compressed).
- `threshold-kb` defaults to `500`, allowing the new APK to grow by at most 500 KB.
- Only growth **above** the threshold fails; `delta <= threshold` passes, and a shrinking APK
  passes.
- A threshold of `0` rejects any growth and is suitable for strict gates.
- Reports contain `apkdiff.json` / `apkdiff.html` / `apkdiff.md` / `size-summary.md` and are kept
  as artifacts on every platform, including failures.

## GitHub Actions

Copy [`github/example-pull-request.yml`](github/example-pull-request.yml) into the Android
repository's `.github/workflows/apk-size.yml` and adjust the project settings:

```yaml
env:
  ANDROID_MODULE: app
  BUILD_TASK: assembleRelease
  SIZE_THRESHOLD_KB: 500
  APKDIFF_TOOL_REF: main
```

For PRs targeting `main`, the workflow builds the base/head APKs, calls
[`github/action.yml`](github/action.yml), generates reports and enforces the threshold.
See [`github/README.md`](github/README.md) for inputs and outputs.

## GitLab CI

Copy [`gitlab/.gitlab-ci.yml`](gitlab/.gitlab-ci.yml) into the repository root:

```bash
cp monitor-apk-size-ci/gitlab/.gitlab-ci.yml .gitlab-ci.yml
```

For merge requests targeting `main`:

1. `build:base` builds the target branch APK;
2. `build:head` builds the MR APK;
3. `apk-size` installs apkdiff, compares, generates reports and enforces
   `SIZE_THRESHOLD_KB`.

Runner, image, baseline and artifact details are in [`gitlab/README.md`](gitlab/README.md).

## Gerrit + Jenkins

Place [`gerrit-jenkins/Jenkinsfile`](gerrit-jenkins/Jenkinsfile) in the Gerrit project and
configure a Gerrit Trigger for `Patchset Created`:

- build the baseline from `merge-base(HEAD, target branch)`;
- build the patchset APK;
- install apkdiff, generate reports and enforce the threshold;
- fail the pipeline and vote `Verified -1` on the Gerrit patchset when it exceeds the threshold;
- archive the report and write the summary to the Gerrit review message.

See [`gerrit-jenkins/README.md`](gerrit-jenkins/README.md) for Gerrit server setup, job trigger,
SCM refspec, permissions and troubleshooting.

## Repository self-test

`.github/workflows/apk-size-monitor-selftest.yml` runs the complete GitHub monitor flow against
the two fixture APKs under `js/tests/fixtures/complex` for PRs to `main` (500 KB threshold). It
verifies action installation, report generation, threshold enforcement and artifact upload.
