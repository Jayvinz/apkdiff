"""Command-line entry point: translate CLI arguments into library calls.

main() runs a pipeline:
    1. parse arguments (APKs, output formats, switches)
    2. analyze the old APK (mapping -> analysis)
    3. analyze the new APK
    4. diff
    5. render requested reports
    6. return exit code 1 when --fail-on-regression and the APK grew

Step 6 is the CI size gate: a non-zero exit code fails the PR check.

Run with `python -m apkdiff ...` or the installed `apkdiff ...` (see __main__.py).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from apkdiff_core import (
    analyze_apk,
    diff_apks,
    load_mapping,
    print_console,
    write_html,
    write_json,
    write_markdown,
)

VALID_FORMATS = ("console", "json", "html", "markdown")


def _autodetect_mapping(apk_path: str) -> str | None:
    """Look for a mapping file next to the APK."""
    apk = Path(apk_path).resolve()
    stem = apk.stem
    candidates = [
        apk.parent / f"{stem}-mapping.txt",
        apk.parent / f"{stem}.mapping.txt",
        apk.parent / "mapping.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apkdiff",
        description="对比两个 APK，按类 / 资源粒度输出体积变更报告。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  apkdiff old.apk new.apk
  apkdiff old.apk new.apk \\
      --old-mapping old/mapping.txt --new-mapping new/mapping.txt \\
      --format console,json,html -o report/

说明:
  类体积为 DEX 中归属于该类的未压缩字节（含 class_def、code、
  debug、annotations、标识符与字符串池）；每个 dex 的压缩贡献按该
  dex 的整体压缩率估算，便于与 APK 实际大小对齐。
""",
    )
    parser.add_argument("old_apk", help="旧版本 APK 路径")
    parser.add_argument("new_apk", help="新版本 APK 路径")
    parser.add_argument("--old-mapping", help="旧版本 ProGuard/R8 mapping.txt（默认自动探测）")
    parser.add_argument("--new-mapping", help="新版本 ProGuard/R8 mapping.txt（默认自动探测）")
    parser.add_argument(
        "--format", default="console,json,html",
        help=f"输出格式，逗号分隔：{','.join(VALID_FORMATS)}（默认 console,json,html）",
    )
    parser.add_argument("-o", "--output", default="apkdiff-report", help="报告输出目录")
    parser.add_argument(
        "--metric", choices=("compressed", "uncompressed"), default="compressed",
        help="排序与 Δ 显示所用的指标（默认 compressed）",
    )
    parser.add_argument("--top", type=int, default=30, help="控制台每种类型显示条数（默认 30）")
    parser.add_argument("--full", action="store_true", help="控制台显示全部条目")
    parser.add_argument("--include-meta", action="store_true", help="把 META-INF 纳入资源对比")
    parser.add_argument("--detect-renames", action="store_true", help="检测内容相同的资源重命名")
    parser.add_argument(
        "--fail-on-regression", action="store_true",
        help="若新 APK 体积增大则以退出码 1 结束（便于 CI 使用）",
    )
    return parser


def _ensure_utf8_output() -> None:
    """Force UTF-8 console output, matching the JVM and Node.js CLIs.

    On Chinese Windows the default pipe/console encoding is GBK, which garbles the
    Chinese report. Legacy consoles may still need `chcp 65001`.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
    invalid = [f for f in formats if f not in VALID_FORMATS]
    if invalid:
        parser.error(f"不支持的输出格式: {', '.join(invalid)}；可选: {', '.join(VALID_FORMATS)}")

    for apk in (args.old_apk, args.new_apk):
        if not os.path.isfile(apk):
            parser.error(f"APK 不存在: {apk}")

    old_mapping_path = args.old_mapping or _autodetect_mapping(args.old_apk)
    new_mapping_path = args.new_mapping or _autodetect_mapping(args.new_apk)

    if "console" in formats:
        print(f"[1/4] 读取旧 APK: {args.old_apk}")
    old_mapping = load_mapping(old_mapping_path)
    old = analyze_apk(args.old_apk, old_mapping)
    if "console" in formats:
        print(f"      类 {len(old.classes)} 个，条目 {len(old.entries)} 个"
              + (f"，mapping: {old_mapping_path}" if old_mapping_path else "（无 mapping）"))
        print(f"[2/4] 读取新 APK: {args.new_apk}")
    new_mapping = load_mapping(new_mapping_path)
    new = analyze_apk(args.new_apk, new_mapping)
    if "console" in formats:
        print(f"      类 {len(new.classes)} 个，条目 {len(new.entries)} 个"
              + (f"，mapping: {new_mapping_path}" if new_mapping_path else "（无 mapping）"))

    if not old.classes and not new.classes:
        print("错误: 两个 APK 中都没有解析出任何 DEX 类。", file=sys.stderr)
        return 2

    if "console" in formats:
        print("[3/4] 计算差异 …")
    result = diff_apks(
        old, new,
        include_meta=args.include_meta,
        detect_renames=args.detect_renames,
    )

    if "console" in formats:
        print("[4/4] 输出报告 …")
        print()
        print_console(result, metric=args.metric, top=args.top, full=args.full)

    out_dir = Path(args.output)
    for fmt in formats:
        if fmt == "console":
            continue
        if fmt == "json":
            target = out_dir / "apkdiff.json"
            write_json(result, str(target), args.metric)
        elif fmt == "html":
            target = out_dir / "apkdiff.html"
            write_html(result, str(target), args.metric)
        elif fmt == "markdown":
            target = out_dir / "apkdiff.md"
            write_markdown(result, str(target), args.metric)
        else:
            continue
        if "console" in formats:
            print(f"  → {target}")

    if "console" not in formats:
        print(f"报告已生成于 {out_dir.resolve()}")

    # Size gate: with --fail-on-regression, return 1 when the new APK grew.
    # A non-zero exit code fails the shell/CI step and blocks the PR check.
    # This is the entire "grew too much => block merge" mechanism.
    if args.fail_on_regression and result.summary["apk_size_delta"] > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
