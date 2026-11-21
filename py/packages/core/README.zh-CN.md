[English](README.md) | 简体中文

# apkdiff-core

APK 包体积 diff 核心库（纯 Python 标准库，零运行时依赖）。

把 DEX 字节归属到类，比较两个 APK 的类与资源，并渲染控制台 / JSON / HTML / Markdown 报告。

## 安装

```bash
pip install apkdiff-core
```

需要 Python 3.7 或更高版本。

## 使用

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

- `analyze_apk(path, mapping=None, hash_content=True)`
- `load_mapping(path)` / `Mapping.parse(path)`
- `diff_apks(old, new, include_meta=False, detect_renames=False)`
- `print_console` / `build_json` / `write_json` / `write_html` / `write_markdown`
- `human_size` / `human_delta`
- 数据类：`ApkAnalysis`、`ApkClass`、`ApkEntry`、`DexAnalysis`、`DexClass`、`Change`、`DiffResult`

报告与 JVM、Node.js 实现逐字节一致。