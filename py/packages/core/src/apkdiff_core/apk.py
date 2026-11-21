"""APK reader: unpack the APK, inventory its entries, and let dex.py analyze each dex.

An APK is a zip archive. This module does two things:

1. Inventory resources: walk every zip entry, record its name, compressed and
   uncompressed size, CRC and SHA-256, and classify it by path (res/, assets/,
   lib/, META-INF/, resources.arsc, ...). Resource diffs use this inventory.

2. Analyze code: find every classes*.dex, let dex.py attribute bytes to classes,
   then map obfuscated class names back through the mapping file.

Compressed-size caveat:
   A dex is compressed as one blob in the zip, so there is no exact way to slice
   "the compressed bytes of one class". We estimate by applying the dex-wide
   compression ratio (compressed size / uncompressed size) to each class's
   uncompressed size. It is an estimate, but it reflects which class grew.

   The default report metric (--metric compressed) uses this estimate.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import zipfile
from dataclasses import dataclass, field

from .dex import DexAnalysis, DexFile, descriptor_to_class_name
from .mapping import Mapping
from .util import SizeBreakdown

_DEX_RE = re.compile(r"^classes\d*\.dex$", re.IGNORECASE)


@dataclass
class ApkEntry:
    name: str
    category: str
    compress_size: int
    file_size: int
    crc: int
    sha256: str

    @property
    def is_resource(self) -> bool:
        # META-INF is opt-in via --include-meta; the filtering happens in
        # diff_apks(), so it must be included in the raw inventory here.
        return self.category in (
            "res", "assets", "resources", "manifest", "lib", "meta", "other"
        )


@dataclass
class ApkClass:
    name: str  # deobfuscated when a mapping was supplied
    raw_name: str  # name as it appears in the dex
    dex: str
    size: int  # uncompressed, attributed DEX bytes
    compressed_size: int  # estimated APK footprint contribution
    breakdown: SizeBreakdown
    content_hash: str
    methods: int
    fields: int
    partial: bool = False
    warning: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "raw_name": self.raw_name,
            "dex": self.dex,
            "size": self.size,
            "compressed_size": self.compressed_size,
            "methods": self.methods,
            "fields": self.fields,
            "breakdown": self.breakdown.as_dict(),
            "content_hash": self.content_hash,
        }


@dataclass
class ApkAnalysis:
    path: str
    file_size: int
    entries: dict[str, ApkEntry] = field(default_factory=dict)
    classes: dict[str, ApkClass] = field(default_factory=dict)
    dex_files: list[DexAnalysis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def resource_entries(self) -> dict[str, ApkEntry]:
        return {k: v for k, v in self.entries.items() if v.is_resource}

    @property
    def total_class_bytes(self) -> int:
        return sum(c.size for c in self.classes.values())

    @property
    def total_class_compressed_bytes(self) -> int:
        return sum(c.compressed_size for c in self.classes.values())

    @property
    def unattributed_dex_bytes(self) -> int:
        return sum(d.unattributed for d in self.dex_files)


def categorize(name: str) -> str:
    n = posixpath.normpath(name).replace("\\", "/")
    if _DEX_RE.match(posixpath.basename(n)) and "/" not in n:
        return "dex"
    if n.startswith("res/"):
        return "res"
    if n.startswith("assets/"):
        return "assets"
    if n.startswith("lib/"):
        return "lib"
    if n.startswith("META-INF/"):
        return "meta"
    if n == "AndroidManifest.xml":
        return "manifest"
    if n == "resources.arsc":
        return "resources"
    return "other"


def analyze_apk(path: str, mapping: Mapping | None = None, hash_content: bool = True) -> ApkAnalysis:
    """Read an APK and build the class / resource inventory."""
    result = ApkAnalysis(path=path, file_size=0)
    try:
        result.file_size = os.stat(path).st_size
    except OSError:
        pass

    try:
        zf = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        result.warnings.append(f"cannot open APK: {exc}")
        return result

    with zf:
        dex_contents: dict[str, bytes] = {}
        infos = zf.infolist()
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            category = categorize(name)
            digest = ""
            if hash_content:
                try:
                    if category == "dex":
                        # Read the dex once: hashing and analysis both need it.
                        content = zf.read(info)
                        digest = hashlib.sha256(content).hexdigest()
                        dex_contents[name] = content
                    else:
                        with zf.open(info, "r") as fh:
                            h = hashlib.sha256()
                            while True:
                                chunk = fh.read(1 << 20)
                                if not chunk:
                                    break
                                h.update(chunk)
                            digest = h.hexdigest()
                except Exception as exc:  # noqa: BLE001
                    result.warnings.append(f"cannot hash {name}: {exc}")
            result.entries[name] = ApkEntry(
                name=name,
                category=category,
                compress_size=info.compress_size,
                file_size=info.file_size,
                crc=info.CRC,
                sha256=digest,
            )

        # Analyze every classes*.dex
        dex_names = sorted(
            (n for n, e in result.entries.items() if e.category == "dex"),
            key=_dex_sort_key,
        )
        for dex_name in dex_names:
            try:
                raw = dex_contents.get(dex_name)
                if raw is None:
                    raw = zf.read(dex_name)
                dex_analysis = DexFile(raw, dex_name=dex_name).analyze()
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(f"cannot analyze {dex_name}: {exc}")
                continue
            result.dex_files.append(dex_analysis)
            result.warnings.extend(f"{dex_name}: {w}" for w in dex_analysis.warnings)

            entry = result.entries[dex_name]
            # Compressed class size is estimated: a dex is compressed as one blob,
            # so we cannot slice per-class compressed bytes. Apply the dex-wide
            # ratio (compressed / uncompressed) to each class's uncompressed size.
            ratio = (entry.compress_size / entry.file_size) if entry.file_size else 0.0
            for cls in dex_analysis.classes:
                if mapping is not None:
                    display_name = mapping.deobfuscate_descriptor(cls.name)
                else:
                    display_name = descriptor_to_class_name(cls.name)
                est_compressed = int(round(cls.size * ratio))
                existing = result.classes.get(display_name)
                if existing is not None:
                    # A class can appear in multiple dex files (rare). Sum its sizes and
                    # combine hashes so it cannot silently disappear.
                    existing.size += cls.size
                    existing.compressed_size += est_compressed
                    existing.breakdown = existing.breakdown.plus(cls.breakdown)
                    existing.content_hash = hashlib.sha256(
                        (existing.content_hash + cls.content_hash).encode("ascii")
                    ).hexdigest()
                    existing.partial = existing.partial or cls.partial
                    existing.warning = " | ".join(filter(None, [existing.warning, cls.warning]))
                else:
                    result.classes[display_name] = ApkClass(
                        name=display_name,
                        raw_name=descriptor_to_class_name(cls.name),
                        dex=dex_name,
                        size=cls.size,
                        compressed_size=est_compressed,
                        breakdown=cls.breakdown,
                        content_hash=cls.content_hash,
                        methods=cls.methods,
                        fields=cls.fields,
                        partial=cls.partial,
                        warning=cls.warning,
                    )

    return result


def _dex_sort_key(name: str) -> tuple[int, str]:
    base = posixpath.basename(name)
    if base.lower() == "classes.dex":
        return (0, name)
    m = re.match(r"classes(\d+)\.dex$", base, re.IGNORECASE)
    return (int(m.group(1)) if m else 9999, name)
