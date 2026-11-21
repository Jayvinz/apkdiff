# 复杂测试用 Android 项目

[English](COMPLEX_FIXTURE.md) | 简体中文

`tests/make_complex_fixture.py` 生成两个版本的“电商 App”源码树和 APK，用于全面验证 apkdiff。
生成物位于 `tests/fixtures/complex/{v1,v2}/`（相对 `py/` 目录），每次运行脚本都会重新生成，并导出 `expected.json`
作为预期变更清单，测试直接读取它而不是硬编码数量。清单里还记录了
`expected_apk_size_delta`（预期 APK 体积增量）和 `apk_size_delta_tolerance`
（允许的浮动范围），供体积回归检查使用；因为 fixture 的 v2 是故意变大的，
不能直接加 `--fail-on-regression`，改由这个预期增量来判断检查是否通过。

以下命令均在 `py/` 目录下执行：

```bash
python tests/make_complex_fixture.py
python -m apkdiff tests/fixtures/complex/v1/v1.apk tests/fixtures/complex/v2/v2.apk \
  --detect-renames --format console,json,html,markdown -o report-complex
```

## 项目结构

```
tests/fixtures/complex/
  expected.json             预期变更清单（类 / 资源 / dex / 类数量）
  v1/
    AndroidManifest.xml
    src/a/ b/                 应用 / Activity / Fragment / Adapter  -> classes.dex
    src/g/ h/ i/              catalog / cart / checkout 业务模块     -> classes.dex
    src/c/ d/ e/ f/           领域 / 数据 / 工具 / 新功能            -> classes2.dex
    src/j/ k/ l/ m/           user / social / media / push 模块      -> classes2.dex
    src/n/ o/ p/ q/ r/        analytics/network/storage/ui/helper    -> classes3.dex
    res/                      values / layout / drawable / mipmap / raw
    assets/                   JSON 配置、嵌套 JSON、SVG 图片、SQLite DB、Web 页面
    lib/                      arm64-v8a / x86 / armeabi-v7a native 库
    mapping.txt               R8 风格类映射（混淆名 -> 业务名）
    v1.apk                    最终 APK（classes.dex + classes2.dex + classes3.dex）
v2/ 同上，但内容按下面的矩阵做了增删改，并新增 explore 业务模块
```

## 业务复杂度覆盖

| DEX 结构 | 对应代码 |
| --- | --- |
| 枚举 | `c.d` OrderStatus + `switch` |
| 接口 / default 方法 | `d.a`、`d.b`、`d.f`、`d.g` 及各 domain 的 `Repository` |
| 注解（RUNTIME，含 String/int/String[] 值） | `e.tr` Traceable，应用于 `a.b`、`c.a`、`e.a` |
| 静态初始化 + 静态常量数组 | `a.a` ShopApplication、`e.d` Constants |
| 内部类 / 匿名类 / 静态嵌套类 | `b.c` / `b.d` 的 `Holder`、`$1`，及 `$Holder`、`$-CC` |
| Lambda（D8 脱糖生成合成类） | `b.a` / `b.b` / explore 模块的 `$$ExternalSyntheticLambda0` |
| 泛型 | `b.a` / `b.b` Adapter `<T>` |
| try/catch 多分支 + catch-all | `a.b`、`d.c`、`d.h` 及各 service / validator |
| packed / sparse switch | `a.b`、`c.d`、`d.c`、`f.b` 及各 service |
| 长字符串、宽类型（long/double） | 各 Activity、Entity、Event |
| PNG 资源 | `res/mipmap-xxhdpi-v4/ic_launcher.png` |
| SVG 资源 / assets | `res/raw/logo.svg`、`assets/images/hero.svg`、`explore.svg`、`legacy.svg` |
| SQLite DB assets | `assets/databases/app.db`、`assets/databases/explore.db` |
| 多 dex（3 个） | `classes.dex` + `classes2.dex` + `classes3.dex` |
| 类级混淆 + mapping | 全部 214 → 225 个业务类，映射为 `com.shop.*` 业务名 |
| 业务分层 | 12 个业务域 × 15 种角色（Repository/Impl/Entity/Dto/UseCase/ViewModel/Adapter/Fragment/Utils/Cache/Mapper/Validator/Service/Event/Worker） |

D8 会为 lambda / 内部类生成额外的合成类（v1 共 298 个类、v2 共 315 个类），这些类没有 mapping 条目，
因此报告里会同时出现「已反混淆业务名」和「原始混淆名（含 `$`）」，正好覆盖混合场景。

## v1 → v2 变更矩阵

完整清单见 `tests/fixtures/complex/expected.json`，测试按该清单逐项精确校验。

**代码类**

| 类型 | 业务类数量 | 说明 |
| --- | --- | --- |
| 修改 | 32 | 5 个手工类 + 按 `(域字母 + 角色名长度) % 4 == 0` 规则选取的 domain 类 |
| 删除 | 8 | `com.shop.ui.CartActivity`、`com.shop.ui.fragment.ProfileFragment` + 6 个 domain 类（及其合成类） |
| 新增 | 19 | 4 个手工类 + 整个 `com.shop.explore.*` 模块（15 个角色，及其合成类） |
| 未变 | 其余 | 用于验证索引池重排不会造成误报（如 `ProductListActivity`、`com.shop.util.Logger`） |

**资源文件**

| 类型 | 数量 | 说明 |
| --- | --- | --- |
| 修改 | 60 | 12 个手工资源（含 SVG / SQLite DB）+ 12 个业务域 × 4 类资源（layout/drawable/raw/assets，均带 -v1/-v2 标记）+ `resources.arsc` / `AndroidManifest.xml` 等 |
| 删除 | 5 | `layout/fragment_home.xml`、`res/raw/legal_notice.txt`、`assets/web/index.html`、`assets/images/legacy.svg`、`lib/armeabi-v7a/libshop.so` |
| 新增 | 11 | `layout/activity_search.xml`、`drawable/bg_accent.xml`、`res/raw/help.txt`、`assets/nested/ui/new_pref.json`、`assets/images/explore.svg`、`assets/databases/explore.db`、`lib/mips/libshop.so` + explore 域资源 |
| 重命名 | 1 | `res/raw/config.json` → `res/raw/settings.json`，内容完全相同（`--detect-renames`） |
| 默认排除 | 2 | `META-INF/MANIFEST.MF`、`META-INF/CERT.SF`（`--include-meta` 可见） |

注意：aapt 会把 `res/values/*.xml` 编译进 `resources.arsc`，并把 `mipmap-xxhdpi` 重命名为
`mipmap-xxhdpi-v4`，因此 APK 内并不存在 `res/values/*.xml` 条目，`expected.json` 按 APK 内实际条目名记录。

## 预期结果

```
APK 文件          92.07 KB → 100.00 KB  Δ +7.93 KB
类:   新增   27  删除   10  修改   32   (旧 298 → 新 315，含合成类)
资源: 新增   11  删除    5  修改   60  重命名 1
解析警告: 0
```

并且满足每个 dex 的 `Σ类归属字节 + unattributed = dex 文件大小`。
这些约束已固化为 `tests/test_apkdiff.py::TestComplexFixture` 的自动化测试（15 个用例全部通过），其中包含 XML / PNG / SVG / SQLite DB / native 库的资源类型覆盖测试。
