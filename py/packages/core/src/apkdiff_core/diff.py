"""Compare two APK analyses and classify every change.

dex.py and apk.py understand one APK; this module understands the difference
between two APKs.

Four change states:
    added    present only in the new APK
    deleted  present only in the old APK
    modified present in both with different content
    renamed  a deleted and an added entry with identical content
             (only with --detect-renames)

Classes compare by semantic fingerprint (see dex.py); resources compare by
SHA-256 content hash.

The summary (APK delta, class/resource counts, ...) is consumed by reporters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .apk import ApkAnalysis, ApkClass, ApkEntry

ADDED = "added"
DELETED = "deleted"
MODIFIED = "modified"
RENAMED = "renamed"
UNCHANGED = "unchanged"

STATUS_LABEL = {
    ADDED: "新增",
    DELETED: "删除",
    MODIFIED: "修改",
    RENAMED: "重命名",
    UNCHANGED: "未变",
}


@dataclass
class Change:
    key: str
    kind: str  # "class" | "resource"
    status: str
    old_size: int  # uncompressed bytes
    new_size: int
    old_compressed: int
    new_compressed: int
    old_hash: str = ""
    new_hash: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def delta(self) -> int:
        return self.new_size - self.old_size

    @property
    def compressed_delta(self) -> int:
        return self.new_compressed - self.old_compressed

    def size_for(self, metric: str) -> int:
        return self.compressed_delta if metric == "compressed" else self.delta

    def old_for(self, metric: str) -> int:
        return self.old_compressed if metric == "compressed" else self.old_size

    def new_for(self, metric: str) -> int:
        return self.new_compressed if metric == "compressed" else self.new_size

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "status": self.status,
            "status_label": STATUS_LABEL.get(self.status, self.status),
            "old_size": self.old_size,
            "new_size": self.new_size,
            "delta": self.delta,
            "old_compressed": self.old_compressed,
            "new_compressed": self.new_compressed,
            "compressed_delta": self.compressed_delta,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "detail": self.detail,
        }


@dataclass
class DiffResult:
    old: ApkAnalysis
    new: ApkAnalysis
    classes: list[Change] = field(default_factory=list)
    resources: list[Change] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def changes(self) -> list[Change]:
        return self.classes + self.resources


def _class_changes(old: ApkAnalysis, new: ApkAnalysis) -> list[Change]:
    out: list[Change] = []
    all_keys = sorted(set(old.classes) | set(new.classes))
    for key in all_keys:
        o: ApkClass | None = old.classes.get(key)
        n: ApkClass | None = new.classes.get(key)
        if o is None and n is not None:
            out.append(Change(
                key=key, kind="class", status=ADDED,
                old_size=0, new_size=n.size, old_compressed=0,
                new_compressed=n.compressed_size, new_hash=n.content_hash,
                detail={
                    "raw_name": n.raw_name, "dex": n.dex,
                    "methods": n.methods, "fields": n.fields,
                    "breakdown": n.breakdown.as_dict(),
                    "partial": n.partial, "warning": n.warning,
                },
            ))
        elif o is not None and n is None:
            out.append(Change(
                key=key, kind="class", status=DELETED,
                old_size=o.size, new_size=0, old_compressed=o.compressed_size,
                new_compressed=0, old_hash=o.content_hash,
                detail={
                    "raw_name": o.raw_name, "dex": o.dex,
                    "methods": o.methods, "fields": o.fields,
                    "breakdown": o.breakdown.as_dict(),
                    "partial": o.partial, "warning": o.warning,
                },
            ))
        else:
            assert o is not None and n is not None
            if o.content_hash == n.content_hash:
                # Present in both. Compare semantic fingerprints, not byte counts:
                # an identical fingerprint means the source did not change, even if index
                # pool reshuffling shifted attributed bytes slightly.
                # Without this, adding one unrelated class would mark almost every class
                # as modified and drown the report.
                continue
            old_breakdown = o.breakdown.as_dict()
            new_breakdown = n.breakdown.as_dict()
            breakdown_delta = {
                k: new_breakdown[k] - old_breakdown[k] for k in old_breakdown
            }
            out.append(Change(
                key=key, kind="class", status=MODIFIED,
                old_size=o.size, new_size=n.size,
                old_compressed=o.compressed_size, new_compressed=n.compressed_size,
                old_hash=o.content_hash, new_hash=n.content_hash,
                detail={
                    "raw_name": n.raw_name,
                    "dex": f"{o.dex} -> {n.dex}" if o.dex != n.dex else n.dex,
                    "methods_before": o.methods, "methods_after": n.methods,
                    "fields_before": o.fields, "fields_after": n.fields,
                    "breakdown_delta": breakdown_delta,
                    "partial": o.partial or n.partial,
                    "warning": " | ".join(filter(None, [o.warning, n.warning])),
                },
            ))
    return out


def _entry_change(
    key: str,
    o: ApkEntry | None,
    n: ApkEntry | None,
    status: str,
    renamed_from: str = "",
) -> Change:
    detail: dict = {"category": n.category if n is not None else o.category}
    if o is not None and n is not None:
        detail["crc_before"] = f"{o.crc:08x}"
        detail["crc_after"] = f"{n.crc:08x}"
        detail["hash_before"] = o.sha256[:16]
        detail["hash_after"] = n.sha256[:16]
        detail["compression_before"] = (
            round((1 - o.compress_size / o.file_size) * 100, 1) if o.file_size else 0
        )
        detail["compression_after"] = (
            round((1 - n.compress_size / n.file_size) * 100, 1) if n.file_size else 0
        )
    if renamed_from:
        detail["renamed_from"] = renamed_from
    return Change(
        key=key,
        kind="resource",
        status=status,
        old_size=o.file_size if o else 0,
        new_size=n.file_size if n else 0,
        old_compressed=o.compress_size if o else 0,
        new_compressed=n.compress_size if n else 0,
        old_hash=o.sha256 if o else "",
        new_hash=n.sha256 if n else "",
        detail=detail,
    )


def _included_entries(apk: ApkAnalysis, include_meta: bool) -> dict[str, ApkEntry]:
    """Resource entries participating in the comparison (META-INF is opt-in)."""
    return {
        name: entry
        for name, entry in apk.resource_entries.items()
        if include_meta or entry.category != "meta"
    }


def _resource_changes(
    old_entries: dict[str, ApkEntry],
    new_entries: dict[str, ApkEntry],
    detect_renames: bool,
) -> list[Change]:
    added = sorted(set(new_entries) - set(old_entries))
    deleted = sorted(set(old_entries) - set(new_entries))

    changes: list[Change] = []
    paired_old: set[str] = set()
    paired_new: set[str] = set()

    if detect_renames:
        # Find renamed files: a deleted old entry and an added new entry with
        # identical content hashes are likely the same file under a new name
        # (for example a drawable renamed).
        # Group deleted files by hash, then match each added file's hash.
        by_hash: dict[str, list[str]] = {}
        for name in deleted:
            h = old_entries[name].sha256
            if h:
                by_hash.setdefault(h, []).append(name)
        for name in added:
            h = new_entries[name].sha256
            candidates = by_hash.get(h, []) if h else []
            if not candidates:
                continue
            old_name = candidates.pop(0)
            if not candidates:
                del by_hash[h]
            paired_old.add(old_name)
            paired_new.add(name)
            changes.append(_entry_change(name, old_entries[old_name], new_entries[name],
                                         RENAMED, renamed_from=old_name))

    for name in sorted(set(new_entries)):
        if name in old_entries:
            o, n = old_entries[name], new_entries[name]
            if o.sha256 != n.sha256 or o.file_size != n.file_size:
                changes.append(_entry_change(name, o, n, MODIFIED))
        elif name not in paired_new:
            changes.append(_entry_change(name, None, new_entries[name], ADDED))

    for name in deleted:
        if name not in paired_old:
            changes.append(_entry_change(name, old_entries[name], None, DELETED))

    return changes


def diff_apks(
    old: ApkAnalysis,
    new: ApkAnalysis,
    include_meta: bool = False,
    detect_renames: bool = False,
) -> DiffResult:
    old_entries = _included_entries(old, include_meta)
    new_entries = _included_entries(new, include_meta)
    classes = _class_changes(old, new)
    resources = _resource_changes(old_entries, new_entries, detect_renames)

    def counts(items: list[Change], status: str) -> int:
        return sum(1 for c in items if c.status == status)

    old_class_bytes = old.total_class_bytes
    new_class_bytes = new.total_class_bytes
    old_class_compressed = old.total_class_compressed_bytes
    new_class_compressed = new.total_class_compressed_bytes
    old_resource_bytes = sum(e.file_size for e in old_entries.values())
    new_resource_bytes = sum(e.file_size for e in new_entries.values())
    old_resource_compressed = sum(e.compress_size for e in old_entries.values())
    new_resource_compressed = sum(e.compress_size for e in new_entries.values())

    summary = {
        "old_apk_size": old.file_size,
        "new_apk_size": new.file_size,
        "apk_size_delta": new.file_size - old.file_size,
        "old_class_bytes": old_class_bytes,
        "new_class_bytes": new_class_bytes,
        "class_bytes_delta": new_class_bytes - old_class_bytes,
        "old_class_compressed": old_class_compressed,
        "new_class_compressed": new_class_compressed,
        "class_compressed_delta": new_class_compressed - old_class_compressed,
        "old_resource_bytes": old_resource_bytes,
        "new_resource_bytes": new_resource_bytes,
        "old_resource_compressed": old_resource_compressed,
        "new_resource_compressed": new_resource_compressed,
        "class_count_old": len(old.classes),
        "class_count_new": len(new.classes),
        "class_added": counts(classes, ADDED),
        "class_deleted": counts(classes, DELETED),
        "class_modified": counts(classes, MODIFIED),
        "resource_added": counts(resources, ADDED),
        "resource_deleted": counts(resources, DELETED),
        "resource_modified": counts(resources, MODIFIED),
        "resource_renamed": counts(resources, RENAMED),
        "dex_unattributed_old": old.unattributed_dex_bytes,
        "dex_unattributed_new": new.unattributed_dex_bytes,
    }
    summary["resource_bytes_delta"] = new_resource_bytes - old_resource_bytes
    summary["resource_compressed_delta"] = (
        new_resource_compressed - old_resource_compressed
    )

    return DiffResult(old=old, new=new, classes=classes, resources=resources, summary=summary)
