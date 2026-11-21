[English](README.md) | 简体中文

# @jayvinz/apkdiff-cli

命令行 APK 体积 diff 工具，安装后提供 `apkdiff` 可执行命令。

## 安装

```bash
npm install -g @jayvinz/apkdiff-cli
```

需要 Node.js 18 或更高版本。

## 使用

```bash
apkdiff old.apk new.apk
apkdiff old.apk new.apk \
  --old-mapping old/mapping.txt --new-mapping new/mapping.txt \
  --detect-renames --format console,json,html,markdown -o report/
```

参数与 Python、JVM、Node.js 版本一致：

| 参数 | 说明 |
| --- | --- |
| `--format` | `console,json,html,markdown`（默认 `console,json,html`） |
| `-o, --output` | 输出目录（默认 `apkdiff-report`） |
| `--metric` | `compressed`（默认）或 `uncompressed` |
| `--top N` | 控制台每种类型显示条数（默认 30） |
| `--full` | 显示全部条目 |
| `--include-meta` | 把 `META-INF/` 纳入资源对比 |
| `--detect-renames` | 检测内容相同的资源重命名 |
| `--fail-on-regression` | 新 APK 变大时退出码为 1 |

也可以不全局安装，直接用 `npx`：

```bash
npx @jayvinz/apkdiff-cli old.apk new.apk
```