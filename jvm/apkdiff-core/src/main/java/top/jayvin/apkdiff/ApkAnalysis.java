package top.jayvin.apkdiff;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Inventory and dex analysis for one APK. */
public class ApkAnalysis {
    private final String path;
    private long fileSize;
    private final LinkedHashMap<String, ApkEntry> entries = new LinkedHashMap<>();
    private final LinkedHashMap<String, ApkClass> classes = new LinkedHashMap<>();
    private final List<DexAnalysis> dexFiles = new ArrayList<>();
    private final List<String> warnings = new ArrayList<>();

    public ApkAnalysis(String path, long fileSize) {
        this.path = path;
        this.fileSize = fileSize;
    }

    public String getPath() {
        return path;
    }

    public long getFileSize() {
        return fileSize;
    }

    public void setFileSize(long fileSize) {
        this.fileSize = fileSize;
    }

    public LinkedHashMap<String, ApkEntry> getEntries() {
        return entries;
    }

    public LinkedHashMap<String, ApkClass> getClasses() {
        return classes;
    }

    public List<DexAnalysis> getDexFiles() {
        return dexFiles;
    }

    public List<String> getWarnings() {
        return warnings;
    }

    /** Resource entries participating in the comparison (META-INF is opt-in). */
    public Map<String, ApkEntry> getResourceEntries() {
        return getResourceEntries(true);
    }

    public Map<String, ApkEntry> getResourceEntries(boolean includeMeta) {
        LinkedHashMap<String, ApkEntry> out = new LinkedHashMap<>();
        for (Map.Entry<String, ApkEntry> entry : entries.entrySet()) {
            ApkEntry value = entry.getValue();
            if (value.isResource() && (includeMeta || !value.getCategory().equals("meta"))) {
                out.put(entry.getKey(), value);
            }
        }
        return out;
    }

    public long totalClassBytes() {
        long total = 0;
        for (ApkClass cls : classes.values()) {
            total += cls.getSize();
        }
        return total;
    }

    public long totalClassCompressedBytes() {
        long total = 0;
        for (ApkClass cls : classes.values()) {
            total += cls.getCompressedSize();
        }
        return total;
    }

    public long unattributedDexBytes() {
        long total = 0;
        for (DexAnalysis dex : dexFiles) {
            total += dex.getUnattributed();
        }
        return total;
    }
}
