"""apkdiff-core: core library for APK size diffs.

Compares two APKs, attributes DEX bytes to classes, computes added/deleted/
modified/renamed classes and resources with size changes, and renders console /
JSON / HTML / Markdown reports.

Typical usage:

    from apkdiff_core import analyze_apk, load_mapping, diff_apks, print_console

    old = analyze_apk("old.apk", load_mapping("old/mapping.txt"))
    new = analyze_apk("new.apk", load_mapping("new/mapping.txt"))
    result = diff_apks(old, new, detect_renames=True)
    print_console(result)

No third-party runtime dependencies.
"""

from .apk import ApkAnalysis, ApkClass, ApkEntry, analyze_apk, categorize
from .dex import (
    DexAnalysis,
    DexClass,
    DexError,
    DexFile,
    descriptor_to_class_name,
)
from .diff import (
    ADDED,
    DELETED,
    MODIFIED,
    RENAMED,
    STATUS_LABEL,
    UNCHANGED,
    Change,
    DiffResult,
    diff_apks,
)
from .mapping import Mapping, load_mapping
from .report import (
    build_json,
    print_console,
    write_html,
    write_json,
    write_markdown,
)
from .util import SizeBreakdown, human_delta, human_size

__version__ = "1.0.0"

__all__ = [
    "ADDED",
    "ApkAnalysis",
    "ApkClass",
    "ApkEntry",
    "Change",
    "DELETED",
    "DexAnalysis",
    "DexClass",
    "DexError",
    "DexFile",
    "DiffResult",
    "MODIFIED",
    "Mapping",
    "RENAMED",
    "STATUS_LABEL",
    "SizeBreakdown",
    "UNCHANGED",
    "analyze_apk",
    "build_json",
    "categorize",
    "descriptor_to_class_name",
    "diff_apks",
    "human_delta",
    "human_size",
    "load_mapping",
    "print_console",
    "write_html",
    "write_json",
    "write_markdown",
]
