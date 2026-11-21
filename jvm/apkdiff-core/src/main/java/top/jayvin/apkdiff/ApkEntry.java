package top.jayvin.apkdiff;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/** One file inside the APK zip. */
public class ApkEntry {
    private static final Set<String> RESOURCE_CATEGORIES = new HashSet<>(Arrays.asList(
            "res", "assets", "resources", "manifest", "lib", "meta", "other"));

    private final String name;
    private final String category;
    private final long compressSize;
    private final long fileSize;
    private final long crc;
    private final String sha256;

    public ApkEntry(
            String name,
            String category,
            long compressSize,
            long fileSize,
            long crc,
            String sha256) {
        this.name = name;
        this.category = category;
        this.compressSize = compressSize;
        this.fileSize = fileSize;
        this.crc = crc;
        this.sha256 = sha256;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public long getCompressSize() {
        return compressSize;
    }

    public long getFileSize() {
        return fileSize;
    }

    public long getCrc() {
        return crc;
    }

    public String getSha256() {
        return sha256;
    }

    /**
     * META-INF is opt-in via {@code --include-meta}; the filtering happens in the differ,
     * so it must be included in the raw inventory here.
     */
    public boolean isResource() {
        return RESOURCE_CATEGORIES.contains(category);
    }
}
