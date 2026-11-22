package top.jayvin.apkdiff;

import java.util.LinkedHashMap;

/** One changed class or resource. */
public class Change {
    private final String key;
    private final String kind; // "class" or "resource"
    private final String status;
    private final long oldSize; // uncompressed bytes
    private final long newSize;
    private final long oldCompressed;
    private final long newCompressed;
    private final String oldHash;
    private final String newHash;
    private final LinkedHashMap<String, Object> detail;

    public Change(
            String key,
            String kind,
            String status,
            long oldSize,
            long newSize,
            long oldCompressed,
            long newCompressed,
            String oldHash,
            String newHash,
            LinkedHashMap<String, Object> detail) {
        this.key = key;
        this.kind = kind;
        this.status = status;
        this.oldSize = oldSize;
        this.newSize = newSize;
        this.oldCompressed = oldCompressed;
        this.newCompressed = newCompressed;
        this.oldHash = oldHash;
        this.newHash = newHash;
        this.detail = detail;
    }

    public String getKey() {
        return key;
    }

    public String getKind() {
        return kind;
    }

    public String getStatus() {
        return status;
    }

    public long getOldSize() {
        return oldSize;
    }

    public long getNewSize() {
        return newSize;
    }

    public long getOldCompressed() {
        return oldCompressed;
    }

    public long getNewCompressed() {
        return newCompressed;
    }

    public String getOldHash() {
        return oldHash;
    }

    public String getNewHash() {
        return newHash;
    }

    public LinkedHashMap<String, Object> getDetail() {
        return detail;
    }

    public long getDelta() {
        return newSize - oldSize;
    }

    public long getCompressedDelta() {
        return newCompressed - oldCompressed;
    }

    public long sizeFor(String metric) {
        return metric.equals("compressed") ? getCompressedDelta() : getDelta();
    }

    public long oldFor(String metric) {
        return metric.equals("compressed") ? oldCompressed : oldSize;
    }

    public long newFor(String metric) {
        return metric.equals("compressed") ? newCompressed : newSize;
    }

    public LinkedHashMap<String, Object> asMap() {
        LinkedHashMap<String, Object> map = new LinkedHashMap<>();
        map.put("key", key);
        map.put("kind", kind);
        map.put("status", status);
        map.put("status_label", DiffStatus.label(status));
        map.put("old_size", oldSize);
        map.put("new_size", newSize);
        map.put("delta", getDelta());
        map.put("old_compressed", oldCompressed);
        map.put("new_compressed", newCompressed);
        map.put("compressed_delta", getCompressedDelta());
        map.put("old_hash", oldHash);
        map.put("new_hash", newHash);
        map.put("detail", detail);
        return map;
    }
}
