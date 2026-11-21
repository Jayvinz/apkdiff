#!/usr/bin/env python3
"""Enforce an APK-size threshold in CI.

The script is shared by the GitHub, GitLab and Jenkins cases. It reads the
apkdiff JSON report produced by:

    apkdiff old.apk new.apk --format json -o apkdiff-size-report

and computes:

    delta     = summary.apk_size_delta = new_apk_size - old_apk_size
    threshold = round(threshold_kb * 1024)
    passed    = delta <= threshold

Only growth ABOVE the threshold fails; an equal delta or a shrinking APK
passes. A threshold of 0 therefore rejects any growth.

Outputs:
  * --summary        writes a Markdown summary (also appended to
                     GITHUB_STEP_SUMMARY when that variable exists)
  * --github-output  appends delta-bytes / delta-kb / threshold-bytes / passed
                     to the file passed by GitHub Actions runner

Exit codes:
  0  delta is within the threshold (or the APK shrank)
  1  delta exceeds the threshold (the CI job must fail)
  2  the report is missing or malformed (the CI job must fail)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _kb(value: int) -> str:
    return f"{value / 1024.0:.2f} KB"


def _signed_kb(value: int) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value / 1024.0:.2f} KB"


def _ensure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _write_summary(path: str | None, text: str) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(text)


def _write_outputs(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="apkdiff.json path")
    parser.add_argument("--threshold-kb", type=float, default=500.0,
                        help="allowed APK growth in KB (default: 500)")
    parser.add_argument("--summary", help="write a Markdown summary to this path")
    parser.add_argument("--github-output", help="append action outputs to this file")
    args = parser.parse_args(argv)

    threshold_bytes = int(round(args.threshold_kb * 1024))
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        summary = report["summary"]
        delta = int(summary["apk_size_delta"])
        old_size = int(summary["old_apk_size"])
        new_size = int(summary["new_apk_size"])
        base_path = report.get("old", {}).get("path", "")
        head_path = report.get("new", {}).get("path", "")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        message = f"APK size check failed: cannot read {args.report}: {exc}"
        print(message, file=sys.stderr)
        _write_summary(args.summary, f"## APK size check\n\n❌ {message}\n")
        _write_outputs(args.github_output, {
            "delta-bytes": "0",
            "delta-kb": "0",
            "threshold-bytes": str(threshold_bytes),
            "passed": "false",
        })
        return 2

    passed = delta <= threshold_bytes
    status = "PASS" if passed else "FAIL"
    icon = "✅" if passed else "❌"
    detail = (
        "APK grew beyond the allowed threshold. "
        "Reduce the size or raise `threshold-kb` in the workflow."
        if not passed else
        "APK growth is within the allowed threshold."
    )

    summary_path = args.summary
    markdown = "\n".join([
        "## APK size check",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| Base APK | `{base_path}` |",
        f"| PR APK | `{head_path}` |",
        f"| Base size | {_kb(old_size)} ({old_size} B) |",
        f"| PR size | {_kb(new_size)} ({new_size} B) |",
        f"| **APK delta** | **{_signed_kb(delta)}** ({delta:+d} B) |",
        f"| Threshold | {_kb(threshold_bytes)} ({threshold_bytes} B) |",
        f"| Result | {icon} {status} |",
        "",
        detail,
        "",
    ])
    _write_summary(summary_path, markdown)
    _write_outputs(args.github_output, {
        "delta-bytes": str(delta),
        "delta-kb": f"{delta / 1024.0:.2f}",
        "threshold-bytes": str(threshold_bytes),
        "passed": "true" if passed else "false",
    })

    print(f"APK delta: {_signed_kb(delta)} ({delta:+d} B)")
    print(f"Threshold: {_kb(threshold_bytes)} ({threshold_bytes} B)")
    print(f"Result:    {status}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())