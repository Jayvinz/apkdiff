"""Shared helpers: size formatting, hashing and the per-class byte breakdown.

1. Size formatting (human_size / human_delta)
   Byte counts render with KB as the smallest unit and two decimals:
   257 -> "0.25 KB", 7685 -> "7.50 KB". human_delta adds a sign.

2. SizeBreakdown
   Records how a class's bytes split across code, debug info, strings, etc.
   The per-class detail in reports comes from this structure.

Kept in one module because dex.py, apk.py and report.py all use it, avoiding
circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass


def _human(num: int | None, signed: bool) -> str:
    """Format a byte count with KB as the smallest unit and 2 decimals."""
    if num is None:
        return "-"
    if signed:
        sign = "+" if num > 0 else ("-" if num < 0 else "")
    else:
        sign = "-" if num < 0 else ""
    n = abs(float(num)) / 1024.0
    for unit in ("KB", "MB", "GB", "TB"):
        if n < 1024.0 or unit == "TB":
            return f"{sign}{n:.2f} {unit}"
        n /= 1024.0
    return f"{sign}{n:.2f} TB"


def human_size(num: int | None) -> str:
    """Human readable size, e.g. 0.25 KB / 7.51 KB / 90.85 KB (2 decimals)."""
    return _human(num, signed=False)


def human_delta(num: int | None) -> str:
    """Signed human readable size change, e.g. +7.51 KB / -0.25 KB."""
    return _human(num, signed=True)


@dataclass
class SizeBreakdown:
    """Where the bytes attributed to a single class came from."""

    def_item: int = 0
    class_data: int = 0
    code: int = 0
    debug_info: int = 0
    annotations: int = 0
    static_values: int = 0
    identifiers: int = 0
    strings: int = 0
    type_lists: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "def_item": self.def_item,
            "class_data": self.class_data,
            "code": self.code,
            "debug_info": self.debug_info,
            "annotations": self.annotations,
            "static_values": self.static_values,
            "identifiers": self.identifiers,
            "strings": self.strings,
            "type_lists": self.type_lists,
        }

    @property
    def total(self) -> int:
        return (
            self.def_item + self.class_data + self.code + self.debug_info
            + self.annotations + self.static_values + self.identifiers
            + self.strings + self.type_lists
        )

    def plus(self, other: SizeBreakdown) -> SizeBreakdown:
        return SizeBreakdown(
            self.def_item + other.def_item,
            self.class_data + other.class_data,
            self.code + other.code,
            self.debug_info + other.debug_info,
            self.annotations + other.annotations,
            self.static_values + other.static_values,
            self.identifiers + other.identifiers,
            self.strings + other.strings,
            self.type_lists + other.type_lists,
        )
