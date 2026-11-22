package top.jayvin.apkdiff;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

/** Full result of comparing two APKs. */
public class DiffResult {
    private final ApkAnalysis old;
    private final ApkAnalysis latest;
    private final List<Change> classes;
    private final List<Change> resources;
    private final LinkedHashMap<String, Object> summary;

    public DiffResult(
            ApkAnalysis old,
            ApkAnalysis latest,
            List<Change> classes,
            List<Change> resources,
            LinkedHashMap<String, Object> summary) {
        this.old = old;
        this.latest = latest;
        this.classes = classes;
        this.resources = resources;
        this.summary = summary;
    }

    public ApkAnalysis getOld() {
        return old;
    }

    public ApkAnalysis getNew() {
        return latest;
    }

    public List<Change> getClasses() {
        return classes;
    }

    public List<Change> getResources() {
        return resources;
    }

    public LinkedHashMap<String, Object> getSummary() {
        return summary;
    }

    public List<Change> getChanges() {
        ArrayList<Change> all = new ArrayList<>(classes);
        all.addAll(resources);
        return all;
    }

    /** Read a numeric summary value as long. */
    public long summaryLong(String key) {
        Object value = summary.get(key);
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        throw new IllegalArgumentException("summary value is not numeric: " + key);
    }
}
