"""Read ProGuard/R8 mapping.txt and restore obfuscated class names.

Release code is usually obfuscated: com.shop.ui.MainActivity becomes a.b.
mapping.txt records "a.b came from com.shop.ui.MainActivity".

Reports should show readable business names, so names are translated through
this table.

Only **class-level** mappings are parsed. Method/field mappings exist in the
file but are not displayed by reports.

A missing mapping file is fine: names from the dex are shown unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dex import descriptor_to_class_name

_CLASS_RE = re.compile(r"^\s*(\S+)\s+->\s+(\S+):\s*$")


@dataclass
class Mapping:
    path: str
    # obfuscated dotted name -> original dotted name
    class_names: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def original_name(self, obfuscated: str) -> str:
        """Resolve a dotted obfuscated class name, longest-prefix safe.

        Falls back to the input when no mapping exists.
        """
        name = obfuscated.strip()
        if name in self.class_names:
            return self.class_names[name]
        # Some R8 versions emit array-ish or generic suffixes; strip them.
        for suffix in ("[]", "..."):
            while name.endswith(suffix):
                name = name[: -len(suffix)]
        return self.class_names.get(name, obfuscated)

    def deobfuscate_descriptor(self, descriptor: str) -> str:
        """'La/b/c;' -> original fully-qualified class name."""
        obfuscated = descriptor_to_class_name(descriptor)
        return self.original_name(obfuscated)

    @classmethod
    def parse(cls, path: str) -> "Mapping":
        mapping = cls(path=path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError as exc:
            mapping.warnings.append(f"cannot read mapping file: {exc}")
            return mapping

        for lineno, line in enumerate(lines, 1):
            # mapping.txt contains comments, method mappings and field mappings.
            # Only class mappings are recognized:
            #   com.shop.ui.MainActivity -> a.b:
            # Other lines (comments or non "original -> obfuscated:" forms) are skipped.
            match = _CLASS_RE.match(line)
            if not match:
                continue
            original, obfuscated = match.group(1), match.group(2)
            if original.startswith("#") or obfuscated.startswith("#"):
                continue
            if obfuscated in mapping.class_names and mapping.class_names[obfuscated] != original:
                mapping.warnings.append(
                    f"line {lineno}: duplicate obfuscated name {obfuscated!r}"
                )
            mapping.class_names[obfuscated] = original
        return mapping


def load_mapping(path: str | None) -> Mapping:
    """Load a mapping file, returning an empty Mapping when path is None."""
    if not path:
        return Mapping(path="")
    return Mapping.parse(path)
