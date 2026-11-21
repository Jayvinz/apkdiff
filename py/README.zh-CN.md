# apkdiff Python 实现

[English](README.md) | 简体中文

纯 Python 标准库实现的 APK 体积 diff，无第三方运行时依赖。拆分为两个 PyPI 包：

| PyPI 包 | 导入名 | 用途 |
| --- | --- | --- |
| `apkdiff-core` | `apkdiff_core` | 核心库，可作为依赖 |
| `apkdiff` | `apkdiff` | CLI，依赖 `apkdiff-core`，安装 `apkdiff` 命令 |

三套实现（Python / JVM / Node.js）生成的报告逐字节一致。

## 环境要求

- Python 3.7 – 3.14。最低 3.7，因为使用内置 `dataclasses` 和
  `from __future__ import annotations`；15 个测试在 3.7.9、3.8–3.14 全部通过。
- 不支持 Python 3.6 及更早（缺内置 dataclasses / future annotations）；3.0 早已 EOL，
  现代 pip/setuptools 也无法安装。

## 安装与运行

```bash
pip install apkdiff
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt \
  --new-mapping new/mapping.txt \
  --format console,json,html,markdown \
  -o report/
```

不指定 mapping 时，会自动探测 APK 同目录的 `<apk名>-mapping.txt`、`<apk名>.mapping.txt`
或 `mapping.txt`。

也支持 `python -m apkdiff ...`。

## 作为库使用

```bash
pip install apkdiff-core
```

```python
from apkdiff_core import (
    analyze_apk,
    diff_apks,
    load_mapping,
    print_console,
    write_html,
    write_json,
    write_markdown,
)

old = analyze_apk("old.apk", load_mapping("old/mapping.txt"))
new = analyze_apk("new.apk", load_mapping("new/mapping.txt"))
result = diff_apks(old, new, include_meta=False, detect_renames=True)

print_console(result, metric="compressed", top=30)
write_json(result, "report/apkdiff.json", "compressed")
write_html(result, "report/apkdiff.html", "compressed")
write_markdown(result, "report/apkdiff.md", "compressed")
```

公开 API：

- `analyze_apk(path, mapping=None, hash_content=True)` → `ApkAnalysis`
- `load_mapping(path)` / `Mapping.parse(path)`
- `diff_apks(old, new, include_meta=False, detect_renames=False)` → `DiffResult`
- `print_console` / `build_json` / `write_json` / `write_html` / `write_markdown`
- `human_size` / `human_delta`
- 数据类：`ApkAnalysis`、`ApkClass`、`ApkEntry`、`DexAnalysis`、`DexClass`、`Change`、
  `DiffResult`、`SizeBreakdown`

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--format` | `console,json,html,markdown`，默认 `console,json,html` |
| `-o, --output` | 报告目录，默认 `apkdiff-report` |
| `--metric` | `compressed`（默认）或 `uncompressed` |
| `--top N` | 控制台每种类型显示条数，默认 30 |
| `--full` | 显示全部条目 |
| `--include-meta` | 把 `META-INF/` 纳入资源对比 |
| `--detect-renames` | 把内容相同的删除 + 新增识别为重命名 |
| `--fail-on-regression` | 新 APK 变大时退出码 1 |

## 开发与测试

```bash
cd py
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e packages/core -e packages/cli

python -m unittest discover -s tests -v
python -m unittest tests.test_apkdiff.TestDiff.test_class_changes -v   # 单个测试
```

测试读取仓库中已提交的 fixture APK；fixture 缺失时会自动跳过。

## 构建与发布

```bash
cd py
pip install build twine
python -m build packages/core
python -m build packages/cli
twine upload packages/core/dist/* packages/cli/dist/*   # 需要 PyPI token
```

两个包版本均为 `1.0.0a1`；`apkdiff` 依赖 `apkdiff-core==1.0.0a1`。
已使用本地 wheel 验证 `pip install apkdiff`。

## 目录结构

```text
packages/core/
  pyproject.toml
  README.md / README.zh-CN.md
  src/apkdiff_core/
    __init__.py  apk.py  dex.py  diff.py  mapping.py  report.py  util.py
packages/cli/
  pyproject.toml
  README.md / README.zh-CN.md
  src/apkdiff/
    __init__.py  __main__.py  cli.py
tests/
  make_fixtures.py / make_complex_fixture.py
  check_size_regression.py
  fixtures/       # 已生成 APK、mapping、expected.json
  test_apkdiff.py # 15 个测试
report-complex/   # 示例报告，也是跨语言逐字节比对的基准
```

## 实现说明

- `dex.py` 把 DEX 字节归属到类；共享池归给第一个引用者。
  `所有类字节 + unattributed == dex 大小`。
- 类变更比较语义指纹，而不是 dex 原始字节。
- 资源对比覆盖所有 zip 条目：XML、PNG/WebP、SVG、JSON/文本、SQLite `.db` assets、
  native `.so`、`resources.arsc`、`AndroidManifest.xml` 等，按大小 / CRC / SHA-256 对比。
- 报告统一 LF 换行。JSON 存精确字节整数；控制台 / HTML / Markdown 显示 KB 两位小数。

各包的 API 细节见
[`packages/core/README.zh-CN.md`](packages/core/README.zh-CN.md) 和
[`packages/cli/README.zh-CN.md`](packages/cli/README.zh-CN.md)。