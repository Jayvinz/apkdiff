package top.jayvin.apkdiff;

import java.util.List;

/** One class parsed from a dex file. */
public class DexClass {
    private final String name;
    private final String dexName;
    private final long size;
    private final SizeBreakdown breakdown;
    private final String contentHash;
    private final int methods;
    private final int fields;
    private final boolean partial;
    private final String warning;
    private final List<String> semanticParts;

    public DexClass(
            String name,
            String dexName,
            long size,
            SizeBreakdown breakdown,
            String contentHash,
            int methods,
            int fields,
            boolean partial,
            String warning,
            List<String> semanticParts) {
        this.name = name;
        this.dexName = dexName;
        this.size = size;
        this.breakdown = breakdown;
        this.contentHash = contentHash;
        this.methods = methods;
        this.fields = fields;
        this.partial = partial;
        this.warning = warning;
        this.semanticParts = semanticParts;
    }

    public String getName() {
        return name;
    }

    public String getDexName() {
        return dexName;
    }

    public long getSize() {
        return size;
    }

    public SizeBreakdown getBreakdown() {
        return breakdown;
    }

    public String getContentHash() {
        return contentHash;
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

    public String getWarning() {
        return warning;
    }

    public List<String> getSemanticParts() {
        return semanticParts;
    }
}
