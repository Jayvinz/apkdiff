package top.jayvin.apkdiff;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Compares two APK analyses and classifies every change.
 *
 * <p>Classes compare by semantic fingerprint (see {@link DexFile}), resources by content
 * SHA-256. Renames are detected only when requested: a deleted entry and an added entry with
 * the same content hash are reported as one rename.</p>
 */
public final class Differ {
    private Differ() {
    }

    public static DiffResult diff(ApkAnalysis old, ApkAnalysis newApk) {
        return diff(old, newApk, false, false);
    }

    public static DiffResult diff(ApkAnalysis old, ApkAnalysis newApk, boolean includeMeta) {
        return diff(old, newApk, includeMeta, false);
    }

    public static DiffResult diff(
            ApkAnalysis old,
            ApkAnalysis newApk,
            boolean includeMeta,
            boolean detectRenames) {
        Map<String, ApkEntry> oldEntries = old.getResourceEntries(includeMeta);
        Map<String, ApkEntry> newEntries = newApk.getResourceEntries(includeMeta);
        List<Change> classes = classChanges(old, newApk);
        List<Change> resources = resourceChanges(oldEntries, newEntries, detectRenames);

        long oldClassBytes = old.totalClassBytes();
        long newClassBytes = newApk.totalClassBytes();
        long oldClassCompressed = old.totalClassCompressedBytes();
        long newClassCompressed = newApk.totalClassCompressedBytes();
        long oldResourceBytes = 0;
        long oldResourceCompressed = 0;
        for (ApkEntry entry : oldEntries.values()) {
            oldResourceBytes += entry.getFileSize();
            oldResourceCompressed += entry.getCompressSize();
        }
        long newResourceBytes = 0;
        long newResourceCompressed = 0;
        for (ApkEntry entry : newEntries.values()) {
            newResourceBytes += entry.getFileSize();
            newResourceCompressed += entry.getCompressSize();
        }

        int classAdded = count(classes, DiffStatus.ADDED);
        int classDeleted = count(classes, DiffStatus.DELETED);
        int classModified = count(classes, DiffStatus.MODIFIED);
        int resourceAdded = count(resources, DiffStatus.ADDED);
        int resourceDeleted = count(resources, DiffStatus.DELETED);
        int resourceModified = count(resources, DiffStatus.MODIFIED);
        int resourceRenamed = count(resources, DiffStatus.RENAMED);

        LinkedHashMap<String, Object> summary = new LinkedHashMap<>();
        summary.put("old_apk_size", old.getFileSize());
        summary.put("new_apk_size", newApk.getFileSize());
        summary.put("apk_size_delta", newApk.getFileSize() - old.getFileSize());
        summary.put("old_class_bytes", oldClassBytes);
        summary.put("new_class_bytes", newClassBytes);
        summary.put("class_bytes_delta", newClassBytes - oldClassBytes);
        summary.put("old_class_compressed", oldClassCompressed);
        summary.put("new_class_compressed", newClassCompressed);
        summary.put("class_compressed_delta", newClassCompressed - oldClassCompressed);
        summary.put("old_resource_bytes", oldResourceBytes);
        summary.put("new_resource_bytes", newResourceBytes);
        summary.put("old_resource_compressed", oldResourceCompressed);
        summary.put("new_resource_compressed", newResourceCompressed);
        summary.put("class_count_old", old.getClasses().size());
        summary.put("class_count_new", newApk.getClasses().size());
        summary.put("class_added", classAdded);
        summary.put("class_deleted", classDeleted);
        summary.put("class_modified", classModified);
        summary.put("resource_added", resourceAdded);
        summary.put("resource_deleted", resourceDeleted);
        summary.put("resource_modified", resourceModified);
        summary.put("resource_renamed", resourceRenamed);
        summary.put("dex_unattributed_old", old.unattributedDexBytes());
        summary.put("dex_unattributed_new", newApk.unattributedDexBytes());
        summary.put("resource_bytes_delta", newResourceBytes - oldResourceBytes);
        summary.put("resource_compressed_delta", newResourceCompressed - oldResourceCompressed);

        return new DiffResult(old, newApk, classes, resources, summary);
    }

    private static int count(List<Change> items, String status) {
        int count = 0;
        for (Change change : items) {
            if (change.getStatus().equals(status)) {
                count++;
            }
        }
        return count;
    }

    private static List<Change> classChanges(ApkAnalysis old, ApkAnalysis newApk) {
        List<Change> out = new ArrayList<>();
        TreeSet<String> allKeys = new TreeSet<>();
        allKeys.addAll(old.getClasses().keySet());
        allKeys.addAll(newApk.getClasses().keySet());
        for (String key : allKeys) {
            ApkClass o = old.getClasses().get(key);
            ApkClass n = newApk.getClasses().get(key);
            if (o == null && n != null) {
                LinkedHashMap<String, Object> detail = new LinkedHashMap<>();
                detail.put("raw_name", n.getRawName());
                detail.put("dex", n.getDex());
                detail.put("methods", n.getMethods());
                detail.put("fields", n.getFields());
                detail.put("breakdown", n.getBreakdown().asMap());
                detail.put("partial", n.isPartial());
                detail.put("warning", n.getWarning());
                out.add(new Change(
                        key, "class", DiffStatus.ADDED,
                        0, n.getSize(), 0, n.getCompressedSize(),
                        "", n.getContentHash(), detail));
            } else if (o != null && n == null) {
                LinkedHashMap<String, Object> detail = new LinkedHashMap<>();
                detail.put("raw_name", o.getRawName());
                detail.put("dex", o.getDex());
                detail.put("methods", o.getMethods());
                detail.put("fields", o.getFields());
                detail.put("breakdown", o.getBreakdown().asMap());
                detail.put("partial", o.isPartial());
                detail.put("warning", o.getWarning());
                out.add(new Change(
                        key, "class", DiffStatus.DELETED,
                        o.getSize(), 0, o.getCompressedSize(), 0,
                        o.getContentHash(), "", detail));
            } else {
                assert o != null && n != null;
                if (o.getContentHash().equals(n.getContentHash())) {
                    // Same semantic fingerprint means the source did not change, even if
                    // index-pool reshuffling shifted the attributed byte counts a little.
                    // Without this, adding one unrelated class would drown the report in
                    // false "modified" entries.
                    continue;
                }
                LinkedHashMap<String, Long> oldBreakdown = o.getBreakdown().asMap();
                LinkedHashMap<String, Long> newBreakdown = n.getBreakdown().asMap();
                LinkedHashMap<String, Long> breakdownDelta = new LinkedHashMap<>();
                for (String k : oldBreakdown.keySet()) {
                    Long newValue = newBreakdown.get(k);
                    breakdownDelta.put(k, (newValue == null ? 0L : newValue) - oldBreakdown.get(k));
                }
                LinkedHashMap<String, Object> detail = new LinkedHashMap<>();
                detail.put("raw_name", n.getRawName());
                detail.put("dex", !o.getDex().equals(n.getDex())
                        ? o.getDex() + " -> " + n.getDex() : n.getDex());
                detail.put("methods_before", o.getMethods());
                detail.put("methods_after", n.getMethods());
                detail.put("fields_before", o.getFields());
                detail.put("fields_after", n.getFields());
                detail.put("breakdown_delta", breakdownDelta);
                detail.put("partial", o.isPartial() || n.isPartial());
                detail.put("warning", Util.joinNonEmpty(o.getWarning(), n.getWarning()));
                out.add(new Change(
                        key, "class", DiffStatus.MODIFIED,
                        o.getSize(), n.getSize(),
                        o.getCompressedSize(), n.getCompressedSize(),
                        o.getContentHash(), n.getContentHash(), detail));
            }
        }
        return out;
    }

    private static Change entryChange(
            String key,
            ApkEntry o,
            ApkEntry n,
            String status,
            String renamedFrom) {
        LinkedHashMap<String, Object> detail = new LinkedHashMap<>();
        detail.put("category", (n != null ? n : o).getCategory());
        if (o != null && n != null) {
            detail.put("crc_before", String.format(Locale.ROOT, "%08x", o.getCrc()));
            detail.put("crc_after", String.format(Locale.ROOT, "%08x", n.getCrc()));
            detail.put("hash_before", first16(o.getSha256()));
            detail.put("hash_after", first16(n.getSha256()));
            detail.put("compression_before", compressionPercent(o.getCompressSize(), o.getFileSize()));
            detail.put("compression_after", compressionPercent(n.getCompressSize(), n.getFileSize()));
        }
        if (renamedFrom != null && !renamedFrom.isEmpty()) {
            detail.put("renamed_from", renamedFrom);
        }
        return new Change(
                key,
                "resource",
                status,
                o != null ? o.getFileSize() : 0,
                n != null ? n.getFileSize() : 0,
                o != null ? o.getCompressSize() : 0,
                n != null ? n.getCompressSize() : 0,
                o != null ? o.getSha256() : "",
                n != null ? n.getSha256() : "",
                detail);
    }

    private static String first16(String value) {
        return value.substring(0, Math.min(16, value.length()));
    }

    private static double compressionPercent(long compressSize, long fileSize) {
        if (fileSize == 0) {
            return 0.0;
        }
        double percent = (1 - (double) compressSize / (double) fileSize) * 100;
        return new BigDecimal(percent).setScale(1, RoundingMode.HALF_EVEN).doubleValue();
    }

    private static List<Change> resourceChanges(
            Map<String, ApkEntry> oldEntries,
            Map<String, ApkEntry> newEntries,
            boolean detectRenames) {
        TreeSet<String> addedSet = new TreeSet<>(newEntries.keySet());
        addedSet.removeAll(oldEntries.keySet());
        List<String> added = new ArrayList<>(addedSet);

        TreeSet<String> deletedSet = new TreeSet<>(oldEntries.keySet());
        deletedSet.removeAll(newEntries.keySet());
        List<String> deleted = new ArrayList<>(deletedSet);

        List<Change> changes = new ArrayList<>();
        Set<String> pairedOld = new HashSet<>();
        Set<String> pairedNew = new HashSet<>();

        if (detectRenames) {
            // Group deleted files by hash, then look for added files with the same hash.
            Map<String, List<String>> byHash = new HashMap<>();
            for (String name : deleted) {
                String h = oldEntries.get(name).getSha256();
                if (!h.isEmpty()) {
                    byHash.computeIfAbsent(h, key -> new ArrayList<>()).add(name);
                }
            }
            for (String name : added) {
                String h = newEntries.get(name).getSha256();
                List<String> candidates = h.isEmpty() ? null : byHash.get(h);
                if (candidates == null || candidates.isEmpty()) {
                    continue;
                }
                String oldName = candidates.remove(0);
                if (candidates.isEmpty()) {
                    byHash.remove(h);
                }
                pairedOld.add(oldName);
                pairedNew.add(name);
                changes.add(entryChange(name, oldEntries.get(oldName), newEntries.get(name),
                        DiffStatus.RENAMED, oldName));
            }
        }

        for (String name : new TreeSet<>(newEntries.keySet())) {
            ApkEntry o = oldEntries.get(name);
            ApkEntry n = newEntries.get(name);
            if (o != null) {
                if (!o.getSha256().equals(n.getSha256()) || o.getFileSize() != n.getFileSize()) {
                    changes.add(entryChange(name, o, n, DiffStatus.MODIFIED, null));
                }
            } else if (!pairedNew.contains(name)) {
                changes.add(entryChange(name, null, n, DiffStatus.ADDED, null));
            }
        }

        for (String name : deleted) {
            if (!pairedOld.contains(name)) {
                changes.add(entryChange(name, oldEntries.get(name), null, DiffStatus.DELETED, null));
            }
        }

        return changes;
    }

}
