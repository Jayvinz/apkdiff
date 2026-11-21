# apkdiff

An APK size diff tool. It compares two APK versions and reports added / deleted / modified
classes and resources with their size changes.

[English](README.md) | [简体中文](README.zh-CN.md)

The repository contains three equivalent implementations. This root README uses **Python** for all
examples; each implementation has its own detailed documentation:

| Implementation | Language | Detailed docs | Packages |
| --- | --- | --- | --- |
| [`py/`](py/) | Python 3.7+ | [`py/README.md`](py/README.md) | PyPI: `apkdiff-core` / `apkdiff` |
| [`jvm/`](jvm/) | Java 11 | [`jvm/README.md`](jvm/README.md) | Maven: `top.jayvin.apkdiff:apkdiff-core` |
| [`js/`](js/) | Node.js 18+ | [`js/README.md`](js/README.md) | npm: `@jayvinz/apkdiff-core` / `@jayvinz/apkdiff-cli` |

All three share the same algorithm, CLI options and report format. For the same fixture APKs,
their JSON / HTML / Markdown reports are **byte-for-byte identical** (LF line endings).

## What it does in plain terms

A release manager asks: "Why did this APK grow by 700 KB?" Opening the APK as a zip shows
thousands of files, but not which class or image grew.

1. **Unpack** — open both APKs as zips and inventory every entry (resources, native libraries,
   manifest, etc.) plus every `classes*.dex`.
2. **Attribute bytes to classes** — charge class-specific structures to each class and assign
   shared pools to the first referencing class (deterministically). Attributed bytes plus
   `unattributed` equal the dex size.
3. **Diff** — compare the old and new inventories, classify each class/resource as added,
   deleted, modified or renamed, and calculate size deltas.
4. **Report** — print a console table or generate HTML / Markdown / JSON reports.

Obfuscated names can be restored with a ProGuard/R8 `mapping.txt`. Change detection uses a
semantic fingerprint instead of raw dex bytes, so index-pool reshuffling does not mark unrelated
classes as modified.

## Python quick start

Requirements: Python 3.7 – 3.14, standard library only.

```bash
pip install apkdiff
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt \
  --new-mapping new/mapping.txt \
  --format console,json,html,markdown \
  -o report/
```

Without explicit mapping options, the CLI looks for `<apk-name>-mapping.txt`,
`<apk-name>.mapping.txt`, or `mapping.txt` next to each APK.

As a library:

```bash
pip install apkdiff-core
```

```python
from apkdiff_core import analyze_apk, diff_apks, load_mapping, write_json

old = analyze_apk("old.apk", load_mapping("old/mapping.txt"))
new = analyze_apk("new.apk", load_mapping("new/mapping.txt"))
result = diff_apks(old, new, detect_renames=True)
write_json(result, "report/apkdiff.json", "compressed")
```

See [`py/README.md`](py/README.md) for local development, building wheels and PyPI publishing.

## CLI options

All three implementations accept the same options:

| Option | Description |
| --- | --- |
| `--format` | `console,json,html,markdown`; default `console,json,html` |
| `-o, --output` | Report directory; default `apkdiff-report` |
| `--metric` | Metric used for sorting and deltas: `compressed` (default) or `uncompressed` |
| `--top N` | Console rows per section; default 30 |
| `--full` | Show all rows in the console |
| `--include-meta` | Include `META-INF/` in resource comparison (excluded by default) |
| `--detect-renames` | Report deleted + added resources with identical content as renames |
| `--fail-on-regression` | Exit with code 1 when the new APK is larger (for CI gates) |

## Output

- Console: totals for APK / code / resources, change counts, and class/resource details sorted by
  impact with per-class byte breakdowns.
- `apkdiff.json`: complete structured data with `delta`, `compressed_delta`, hashes and details.
- `apkdiff.html`: self-contained report with search, status filters and sortable columns.
- `apkdiff.md`: Markdown tables suitable for a repository or PR diff.

## Size accounting

### Classes

Every `classes*.dex` is parsed. Class-owned structures (`class_def`, `class_data`, `code`,
`debug_info`, annotations, static values) are charged directly. Shared pools (`type_ids`,
`field_ids`, `method_ids`, `proto_ids`, `string_data`, type lists) are charged to the
deterministically first referencing class. The remainder goes to `unattributed`, preserving:

```text
sum of all class bytes + unattributed = dex file size
```

Each dex's compressed contribution is estimated by applying its overall compression ratio
(`compress_size / file_size`) to each class. This is an estimate, not an exact compressed slice.

Change detection uses a semantic fingerprint (class name, superclass, interfaces, field/method
signatures, debug local names, annotations, source file) rather than raw dex bytes. Adding or
removing a class renumbers index pools; raw-byte comparison would mark almost everything as
modified.

### Resources

APK zip entries are compared by name, recording compressed / uncompressed size, CRC and SHA-256.
All entry types are covered: resource XML, PNG/WebP, SVG, JSON/HTML/text, SQLite `.db` assets,
native `.so` libraries, `resources.arsc`, `AndroidManifest.xml`, and other files.

- Added: only in the new APK
- Deleted: only in the old APK
- Modified: present in both with a different content hash
- Renamed: with `--detect-renames`, a deleted and an added entry with the same hash

`META-INF/` is excluded by default and included with `--include-meta`.

## Tests and fixtures

Two fixture sets were generated with the real Android toolchain (javac + d8 + aapt):

1. **Small fixture**: 3 classes, quick smoke test.
2. **Complex fixture**: a simulated e-commerce app, 214 → 225 business classes, 3 dex files,
   80+ resources (XML, PNG, SVG, JSON, SQLite DB, native libs), and controlled additions /
   deletions / modifications plus a resource rename. See
   [`py/tests/COMPLEX_FIXTURE.md`](py/tests/COMPLEX_FIXTURE.md).

Fixtures are duplicated at `py/tests/fixtures`, `jvm/tests/fixtures` and `js/tests/fixtures` so
each implementation can test independently. The Python copy is the generation source; after
regenerating, copy it to the other two.

```bash
# Python (15 tests; install the two local packages first, see py/README.md)
cd py && python -m unittest discover -s tests -v
```

The JVM suite (21 tests) and Node.js suite (23 tests, including a byte-for-byte comparison with
the Python reports) are documented in [`jvm/README.md`](jvm/README.md) and
[`js/README.md`](js/README.md).

## APK size CI monitoring

[`monitor-apk-size-ci/`](monitor-apk-size-ci/) contains integrations for business repositories:

- GitHub Actions: composite action + PR workflow;
- GitLab CI: merge-request pipeline;
- Gerrit + Jenkins: patchset pipeline with `Verified` voting.

All three compare a baseline APK with the PR / patchset APK, generate
`apkdiff.json` / `apkdiff.html` / `apkdiff.md` / `size-summary.md`, and fail when
`apk_size_delta > threshold`. The threshold defaults to **500 KB**. See
[`monitor-apk-size-ci/IMPLEMENTATION.md`](monitor-apk-size-ci/IMPLEMENTATION.md).

This repository's `.github/workflows/apk-size-monitor-selftest.yml` runs the GitHub flow against
the fixture APKs for PRs to `main`.

## Repository layout

```text
py/          Python implementation and detailed docs
jvm/         Java 11 implementation and detailed docs
js/          Node.js implementation and detailed docs
monitor-apk-size-ci/   GitHub / GitLab / Gerrit+Jenkins size-gate integrations
tests/fixtures under each implementation are kept in sync
```

## Known limitations

- Only classes inside dex files are counted; Kotlin metadata / Compose-generated semantics are
  not parsed.
- Resources are compared by entry name; resource ID reshuffling inside `resources.arsc` is not
  expanded per item.
- No full R8 symbol restoration; only class-level deobfuscation.
- Native `.so` files are not analyzed at symbol level.