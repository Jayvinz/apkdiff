# Gerrit + Jenkins case

[English](README.md) | [简体中文](README.zh-CN.md)

Shared flow, baseline selection, threshold semantics and the report contract are described in
[`../IMPLEMENTATION.md`](../IMPLEMENTATION.md).

`Jenkinsfile` implements a complete Gerrit patchset size gate:

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
        ├─ check-size-threshold.py (default 500 KB)
        └─ archive report + Gerrit Verified vote/comment
```

The threshold defaults to **500 KB**. When the delta exceeds it, the pipeline fails and votes
`Verified -1` on the Gerrit patchset, blocking submit.

## Directory contents

| File | Description |
| --- | --- |
| `Jenkinsfile` | Declarative Pipeline with per-stage comments |
| `../../scripts/check-size-threshold.py` | Shared threshold check used by all platforms |

## 1. Prerequisites

### Jenkins agent

- Labelled `android` (adjust `agent { label 'android' }`).
- JDK + Android SDK capable of building the project.
- `python3` (3.9+), `python3-venv`, `curl`, `git`.
- Network access to GitHub (apkdiff installation and threshold script), or internal PyPI /
  mirror equivalents.
- Do not enable a shallow SCM clone, or ensure the target branch can be fetched; the pipeline
  runs `git fetch origin refs/heads/<target>` and computes `merge-base`.

### Jenkins plugins

- **Gerrit Trigger**: receives Gerrit events and checks out the patchset.
- **Pipeline** (built in).
- Optional: Timestamper, Workspace Cleanup, etc.

### Gerrit permissions

The Jenkins Gerrit account needs:

- SSH access to Gerrit (usually port 29418);
- read access to the target project;
- permission to vote `Verified` (and `Code-Review` if required) on the target branch;
- the account bound in the Gerrit Trigger server configuration when using the `gerritReview`
  step.

## 2. Configure Gerrit Trigger

Manage Jenkins → **Gerrit Trigger** → **Add New Server**:

| Field | Example |
| --- | --- |
| Name | `gerrit` |
| Hostname | `gerrit.example.com` |
| SSH Port | `29418` |
| Username | `jenkins` |
| SSH Key | private key from Jenkins credentials |
| Frontend URL | `https://gerrit.example.com` |

Configure the Jenkins job:

1. Create a Pipeline job (Pipeline script from SCM); point SCM at the Gerrit project.
2. Set the Git SCM **Refspec** to:
   ```text
   ${GERRIT_REFSPEC}
   ```
3. Set **Branch Specifier** to:
   ```text
   ${GERRIT_PATCHSET_REVISION}
   ```
   or use the `FETCH_HEAD` configuration recommended by Gerrit Trigger.
4. Enable **Honor refspec on initial clone**.
5. Under **Gerrit Trigger**, add:
   - Project: the target project, e.g. `my/android/app`;
   - Branch: `refs/heads/main` (or `main`, depending on plugin version);
   - Event: **Patchset Created**.
6. Save; a Gerrit patchset now triggers a build.

`checkout scm` in the Jenkinsfile relies on the SCM configuration above. If the job only has an
inline Pipeline (no SCM), replace it with an explicit `git` / `checkout([$class: 'GitSCM', ...])`
step.

## 3. Job parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `SIZE_THRESHOLD_KB` | `500` | Maximum allowed APK growth in KB |
| `APKDIFF_REF` | `main` | apkdiff git ref; pin to a tag/SHA in production |
| `ANDROID_MODULE` | `app` | Gradle module |
| `BUILD_TASK` | `assembleRelease` | Gradle build task |

Defaults can be overridden per job or manual build.

## 4. Pipeline stages

1. **Checkout patchset**
   - Prints `GERRIT_PROJECT`, `GERRIT_BRANCH`, `GERRIT_PATCHSET_NUMBER` and
     `GERRIT_PATCHSET_REVISION` for troubleshooting.
   - `checkout scm` uses the Gerrit Trigger / Git SCM configuration.

2. **Build baseline APK**
   - `git fetch origin refs/heads/${GERRIT_BRANCH}`;
   - `git merge-base HEAD origin/${GERRIT_BRANCH}` gives the baseline commit;
   - builds in the `base-src` worktree;
   - copies the artifact to `artifacts/base.apk`.

3. **Build patchset APK**
   - builds Gradle in the current workspace (the patchset);
   - copies the artifact to `artifacts/head.apk`.

4. **APK size gate**
   - creates `.apkdiff-venv` and installs apkdiff;
   - downloads the shared threshold script;
   - generates `apkdiff-size-report/{apkdiff.json,apkdiff.html,apkdiff.md}`;
   - runs the threshold script and records PASS/FAIL;
   - calls `error()` when the threshold is exceeded, causing pipeline FAILURE.

5. **post always**
   - `archiveArtifacts` keeps the report;
   - calls `gerritReview`:
     - PASS → `Verified +1`;
     - FAIL / build failure → `Verified -1`;
     - the message contains `size-summary.md`.

## 5. Baseline selection

The example uses:

```bash
base_sha="$(git merge-base HEAD "origin/${GERRIT_BRANCH}")"
```

This compares the patchset against its fork point from the target branch, so commits merged
after the patchset was created are not counted.

To compare against the previous release instead, download a fixed baseline APK and remove the
`Build baseline APK` stage:

```groovy
stage('Download baseline APK') {
  steps {
    sh 'mkdir -p artifacts && curl -fL "$BASELINE_APK_URL" -o artifacts/base.apk'
  }
}
```

## 6. Threshold

```bash
python check-size-threshold.py \
  --report apkdiff-size-report/apkdiff.json \
  --threshold-kb 500 \
  --summary apkdiff-size-report/size-summary.md
```

- Default 500 KB;
- `delta <= threshold` passes;
- only **growth above** the threshold fails;
- a shrinking APK passes;
- `0` rejects any growth.

## 7. Gerrit review

The Jenkinsfile uses the Gerrit Trigger `gerritReview` step:

```groovy
gerritReview(
  labels: [Verified: passed ? 1 : -1],
  message: "APK size gate: ${passed ? 'PASS' : 'FAIL'}\n\n${summary}"
)
```

If the plugin version does not provide this step, or SSH is preferred:

```bash
vote=1
[ "${SIZE_PASSED}" = "true" ] || vote=-1

ssh -p 29418 jenkins@gerrit.example.com \
  gerrit review \
  --verified "${vote}" \
  --message "APK size gate: ${SIZE_PASSED} (see Jenkins report)" \
  "${GERRIT_PATCHSET_REVISION}"
```

Notes:

- `--verified 1/0/-1` requires the corresponding label permission;
- very long messages are truncated by Gerrit; the summary is intentionally small;
- remove `labels` to leave only a comment.

## 8. Report artifacts

The `apkdiff-size-report/` directory is archived:

```text
apkdiff.json
apkdiff.html
apkdiff.md
size-summary.md
```

It is archived on failure as well. To retain the APKs too, extend `archiveArtifacts` in `post`:

```groovy
artifacts: "apkdiff-size-report/**,artifacts/**"
```

APKs are large; apply the team's retention policy.

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| Gerrit events do not trigger the job | Gerrit Trigger server, project/branch filters, event configuration |
| `checkout scm` is empty | Job configured with Git SCM, not an inline-only Pipeline |
| `GERRIT_BRANCH` is empty | Manual build without Gerrit context; the pipeline falls back to `main` |
| `merge-base` fails | Target branch not fetched; disable shallow clone or fetch more history |
| APK not found | `ANDROID_MODULE` / `BUILD_TASK` / variant output path |
| Python venv creation fails | Is `python3-venv` installed on the agent? |
| apkdiff installation fails | Agent access to GitHub; use an internal mirror / PyPI |
| Gerrit vote fails | Jenkins Gerrit account permission and plugin server config |
| Threshold result looks wrong | Is the report path `apkdiff.json`, not HTML/Markdown? |

## 10. Differences from other cases

- GitHub / GitLab manage artifacts and failure status in the CI platform;
- Gerrit + Jenkins additionally writes the result back to code review (`Verified` label +
  comment), so the gate appears on the patchset page;
- all three cases share the same threshold script and apkdiff report format.
