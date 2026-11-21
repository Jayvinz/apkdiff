package top.jayvin.apkdiff;

import java.util.ArrayList;
import java.util.List;

/** Result of analysing one dex file. */
public class DexAnalysis {
    private final String path;
    private final long fileSize;
    private final List<DexClass> classes = new ArrayList<>();
    private long unattributed;
    private final List<String> warnings = new ArrayList<>();

    public DexAnalysis(String path, long fileSize) {
        this.path = path;
        this.fileSize = fileSize;
    }

    public String getPath() {
        return path;
    }

    public long getFileSize() {
        return fileSize;
    }

    public List<DexClass> getClasses() {
        return classes;
    }

    public long getUnattributed() {
        return unattributed;
    }

    public void setUnattributed(long unattributed) {
        this.unattributed = unattributed;
    }

    public List<String> getWarnings() {
        return warnings;
    }
}
