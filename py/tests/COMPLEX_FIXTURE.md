# Complex Android fixture

[English](COMPLEX_FIXTURE.md) | [简体中文](COMPLEX_FIXTURE.zh-CN.md)

`tests/make_complex_fixture.py` generates two versions of an "e-commerce app" source tree and APK
to exercise apkdiff end to end. Outputs are written to `tests/fixtures/complex/{v1,v2}/` relative
to `py/`. Each run regenerates both versions and exports `expected.json` as the expected change
list; tests read that manifest instead of hard-coding counts. It also records
`expected_apk_size_delta` and `apk_size_delta_tolerance` for the size-regression check. Because
the fixture intentionally makes v2 larger, the check cannot use `--fail-on-regression` directly;
it compares the actual delta against the expected range instead.

Run these commands from `py/`:

```bash
python tests/make_complex_fixture.py
python -m apkdiff tests/fixtures/complex/v1/v1.apk tests/fixtures/complex/v2/v2.apk \
  --detect-renames --format console,json,html,markdown -o report-complex
```

## Project structure

```text
tests/fixtures/complex/
  expected.json             expected changes (classes / resources / dex / class counts)
  v1/
    AndroidManifest.xml
    src/a/ b/                 app / Activity / Fragment / Adapter       -> classes.dex
    src/g/ h/ i/              catalog / cart / checkout modules         -> classes.dex
    src/c/ d/ e/ f/           domain / data / utils / new feature       -> classes2.dex
    src/j/ k/ l/ m/           user / social / media / push modules      -> classes2.dex
    src/n/ o/ p/ q/ r/        analytics/network/storage/ui/helper       -> classes3.dex
    res/                      values / layout / drawable / mipmap / raw
    assets/                   JSON configs, nested JSON, SVG images, SQLite DBs, web page
    lib/                      arm64-v8a / x86 / armeabi-v7a native libs
    mapping.txt               R8-style class map (obfuscated -> business name)
    v1.apk                    final APK (classes.dex + classes2.dex + classes3.dex)
v2/ same layout, with additions/deletions/modifications below plus an explore module
```

## Complexity coverage

| DEX structure | Corresponding code |
| --- | --- |
| Enums | `c.d` OrderStatus + `switch` |
| Interfaces / default methods | `d.a`, `d.b`, `d.f`, `d.g`, and each domain's `Repository` |
| Annotations (RUNTIME, String/int/String[] values) | `e.tr` Traceable on `a.b`, `c.a`, `e.a` |
| Static initialization + static constant arrays | `a.a` ShopApplication, `e.d` Constants |
| Inner / anonymous / static nested classes | `Holder`, `$1` in `b.c` / `b.d`, plus `$Holder`, `$-CC` |
| Lambdas (D8 desugared synthetic classes) | `b.a` / `b.b` / `$$ExternalSyntheticLambda0` in explore |
| Generics | `b.a` / `b.b` Adapter `<T>` |
| Multi-branch try/catch + catch-all | `a.b`, `d.c`, `d.h`, each service / validator |
| Packed / sparse switch | `a.b`, `c.d`, `d.c`, `f.b`, each service |
| Long strings, wide types (long/double) | Activities, Entities, Events |
| PNG resource | `res/mipmap-xxhdpi-v4/ic_launcher.png` |
| SVG resources / assets | `res/raw/logo.svg`, `assets/images/hero.svg`, `explore.svg`, `legacy.svg` |
| SQLite database assets | `assets/databases/app.db`, `assets/databases/explore.db` |
| Multiple dex files (3) | `classes.dex` + `classes2.dex` + `classes3.dex` |
| Class-level obfuscation + mapping | all 214 → 225 business classes mapped to `com.shop.*` |
| Business layering | 12 domains × 15 roles (Repository/Impl/Entity/Dto/UseCase/ViewModel/Adapter/Fragment/Utils/Cache/Mapper/Validator/Service/Event/Worker) |

D8 generates extra synthetic classes for lambdas / inner classes (298 classes in v1, 315 in v2).
They have no mapping entries, so reports contain both deobfuscated business names and raw
obfuscated names containing `$`, covering the mixed scenario.

## v1 → v2 change matrix

The complete list is in `tests/fixtures/complex/expected.json`; tests check it item by item.

**Classes**

| Type | Business classes | Description |
| --- | --- | --- |
| Modified | 32 | 5 manual classes + domain classes selected by `(domain letter + role name length) % 4 == 0` |
| Deleted | 8 | `com.shop.ui.CartActivity`, `com.shop.ui.fragment.ProfileFragment` + 6 domain classes (and synthetics) |
| Added | 19 | 4 manual classes + the whole `com.shop.explore.*` module (15 roles and synthetics) |
| Unchanged | rest | Verifies index-pool reshuffling does not create false positives (e.g. `ProductListActivity`, `com.shop.util.Logger`) |

**Resources**

| Type | Count | Description |
| --- | --- | --- |
| Modified | 60 | 12 manual resources (including SVG / SQLite DB) + 12 domains × 4 resource kinds (layout/drawable/raw/assets, marked -v1/-v2) + `resources.arsc` / `AndroidManifest.xml` etc. |
| Deleted | 5 | `layout/fragment_home.xml`, `res/raw/legal_notice.txt`, `assets/web/index.html`, `assets/images/legacy.svg`, `lib/armeabi-v7a/libshop.so` |
| Added | 11 | `layout/activity_search.xml`, `drawable/bg_accent.xml`, `res/raw/help.txt`, `assets/nested/ui/new_pref.json`, `assets/images/explore.svg`, `assets/databases/explore.db`, `lib/mips/libshop.so` + explore resources |
| Renamed | 1 | `res/raw/config.json` → `res/raw/settings.json`, identical content (`--detect-renames`) |
| Excluded by default | 2 | `META-INF/MANIFEST.MF`, `META-INF/CERT.SF` (visible with `--include-meta`) |

Note: aapt compiles `res/values/*.xml` into `resources.arsc` and renames `mipmap-xxhdpi` to
`mipmap-xxhdpi-v4`, so `res/values/*.xml` entries do not exist inside the APK. `expected.json`
records the actual APK entry names.

## Expected result

```text
APK file          92.07 KB → 100.00 KB  Δ +7.93 KB
Classes: added 27  deleted 10  modified 32   (298 → 315 including synthetics)
Resources: added 11  deleted 5  modified 60  renamed 1
Parse warnings: 0
```

Every dex also satisfies `sum(class bytes) + unattributed = dex file size`. These constraints are
covered by `tests/test_apkdiff.py::TestComplexFixture` (all 15 tests pass), including an explicit resource-type coverage test (XML / PNG / SVG / SQLite DB / native lib).
