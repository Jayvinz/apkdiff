package top.jayvin.apkdiff;

import java.util.LinkedHashMap;

/** A class in the APK, with its deobfuscated display name and attributed bytes. */
public class ApkClass {
    private final String name;
    private final String rawName;
    private final String dex;
    private long size;
    private long compressedSize;
    private SizeBreakdown breakdown;
    private String contentHash;
    private final int methods;
    private final int fields;
    private boolean partial;
    private String warning;

    public ApkClass(
            String name,
            String rawName,
            String dex,
            long size,
            long compressedSize,
            SizeBreakdown breakdown,
            String contentHash,
            int methods,
            int fields,
            boolean partial,
            String warning) {
        this.name = name;
        this.rawName = rawName;
        this.dex = dex;
        this.size = size;
        this.compressedSize = compressedSize;
        this.breakdown = breakdown;
        this.contentHash = contentHash;
        this.methods = methods;
        this.fields = fields;
        this.partial = partial;
        this.warning = warning;
    }

    public String getName() {
        return name;
    }

    public String getRawName() {
        return rawName;
    }

    public String getDex() {
        return dex;
    }

    /** Uncompressed, attributed DEX bytes. */
    public long getSize() {
        return size;
    }

    public void setSize(long size) {
        this.size = size;
    }

    /** Estimated APK footprint contribution. */
    public long getCompressedSize() {
        return compressedSize;
    }

    public void setCompressedSize(long compressedSize) {
        this.compressedSize = compressedSize;
    }

    public SizeBreakdown getBreakdown() {
        return breakdown;
    }

    public void setBreakdown(SizeBreakdown breakdown) {
        this.breakdown = breakdown;
    }

    public String getContentHash() {
        return contentHash;
    }

    public void setContentHash(String contentHash) {
        this.contentHash = contentHash;
    }

    public int getMethods() {
        return methods;
    }

    public int getFields() {
        return fields;
    }

    public boolean isPartial() {
        return partial;
    }

    public void setPartial(boolean partial) {
        this.partial = partial;
    }

    public String getWarning() {
        return warning;
    }

    public void setWarning(String warning) {
        this.warning = warning;
    }

    public LinkedHashMap<String, Object> asMap() {
        LinkedHashMap<String, Object> map = new LinkedHashMap<>();
        map.put("name", name);
        map.put("raw_name", rawName);
        map.put("dex", dex);
        map.put("size", size);
        map.put("compressed_size", compressedSize);
        map.put("methods", methods);
        map.put("fields", fields);
        map.put("breakdown", breakdown.asMap());
        map.put("content_hash", contentHash);
        return map;
    }
}
