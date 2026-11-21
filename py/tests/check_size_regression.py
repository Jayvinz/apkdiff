"""Size-regression check: a CI gate for the bundled fixtures.

The bundled fixture intentionally makes v2 larger than v1 so we can verify that
apkdiff reports growth. Adding --fail-on-regression to this fixture pair would
always fail (v2 is supposed to be larger), so CI uses another check:

    1. run apkdiff and generate a JSON report;
    2. this script reads summary.apk_size_delta (the measured delta);
    3. it reads expected_apk_size_delta from expected.json;
    4. inside the allowed range -> pass (exit 0); outside -> fail (exit 1).

This is a regression test for apkdiff's size accounting: if a change breaks the
calculation, the measured delta drifts outside the expected range.

Real projects should not use this "expected delta" logic. Compare a baseline
APK with the build under test and use --fail-on-regression directly; any growth
then fails the check. See the README for CI integration.

Usage:
    python tests/check_size_regression.py <apkdiff.json> <expected.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _kb(num: int) -> str:
    """Format a byte count as KB (same convention as reports: KB + 2 decimals)."""
    return f"{num / 1024.0:.2f} KB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 apkdiff 报告里的体积增量是否在预期范围内。"
    )
    parser.add_argument("report", help="apkdiff 生成的 apkdiff.json 路径")
    parser.add_argument("expected", help="fixture 的 expected.json 路径")
    args = parser.parse_args(argv)

    # Both input files must be readable; otherwise the check fails.
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] 读取输入文件失败: {exc}", file=sys.stderr)
        return 1

    # Read the measured delta. A missing field means the report schema changed.
    try:
        actual = report["summary"]["apk_size_delta"]
    except (KeyError, TypeError):
        print("[FAIL] 报告里找不到 summary.apk_size_delta，报告格式可能变了", file=sys.stderr)
        return 1

    # Read the expected delta and tolerance. Missing tolerance means exact match.
    if "expected_apk_size_delta" not in expected:
        print("[FAIL] expected.json 里缺少 expected_apk_size_delta", file=sys.stderr)
        return 1
    want = expected["expected_apk_size_delta"]
    tolerance = int(expected.get("apk_size_delta_tolerance", 0))

    low, high = want - tolerance, want + tolerance

    # Core check: actual must fall within [want - tolerance, want + tolerance].
    if low <= actual <= high:
        print(
            f"[PASS] APK 体积增量 {_kb(actual)} ({actual} B) "
            f"在预期范围 {_kb(low)} ~ {_kb(high)} 内，回归检查通过。"
        )
        return 0

    # Out of range: print a clear message for the PR checks log.
    print(
        f"[FAIL] APK 体积增量 {_kb(actual)} ({actual} B) "
        f"超出预期范围 {_kb(low)} ~ {_kb(high)} "
        f"(期望 {_kb(want)} ± {_kb(tolerance)})，回归检查失败。",
        file=sys.stderr,
    )
    print(
        "       如果是故意调整了 fixture 的体积，请同步更新 "
        "tests/fixtures/complex/expected.json 里的 expected_apk_size_delta。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
