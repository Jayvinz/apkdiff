package top.jayvin.apkdiff;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * APK reader: opens the APK as a zip, inventories entries (category + compressed/uncompressed
 * size + CRC + SHA-256), and lets {@link DexFile} analyse every {@code classes*.dex}.
 *
 * <p>Compressed class size is an estimate: a dex is compressed as one blob, so there is no
 * way to slice "this class's compressed bytes" out of the stream. The dex-wide compression
 * ratio (compress_size / file_size) is applied to each class's uncompressed size instead.</p>
 */
public final class ApkAnalyzer {
    private static final Pattern DEX_RE =
            Pattern.compile("^classes\\d*\\.dex$", Pattern.CASE_INSENSITIVE);
    private static final Pattern DEX_NUMBER_RE =
            Pattern.compile("^classes(\\d+)\\.dex$", Pattern.CASE_INSENSITIVE);

    private ApkAnalyzer() {
    }

    /** POSIX-style path normalisation (the subset needed by zip entry names). */
    static String posixNormpath(String path) {
        String normalized = path.replace('\\', '/');
        if (normalized.isEmpty()) {
            return ".";
        }
        boolean absolute = normalized.startsWith("/");
        boolean trailingSlash = normalized.endsWith("/");
        List<String> out = new ArrayList<>();
        for (String part : normalized.split("/", -1)) {
            if (part.isEmpty() || part.equals(".")) {
                continue;
            }
            if (part.equals("..")) {
                if (!out.isEmpty() && !out.get(out.size() - 1).equals("..")) {
                    out.remove(out.size() - 1);
                } else if (!absolute) {
                    out.add("..");
                }
            } else {
                out.add(part);
            }
        }
        String joined = String.join("/", out);
        if (absolute) {
            String result = "/" + joined;
            return trailingSlash && !result.endsWith("/") ? result + "/" : result;
        }
        if (joined.isEmpty()) {
            return ".";
        }
        return trailingSlash ? joined + "/" : joined;
    }

    public static String categorize(String name) {
        String normalized = posixNormpath(name).replace('\\', '/');
        String base = normalized.substring(normalized.lastIndexOf('/') + 1);
        if (DEX_RE.matcher(base).matches() && !normalized.contains("/")) {
            return "dex";
        }
        if (normalized.startsWith("res/")) {
            return "res";
        }
        if (normalized.startsWith("assets/")) {
            return "assets";
        }
        if (normalized.startsWith("lib/")) {
            return "lib";
        }
        if (normalized.startsWith("META-INF/")) {
            return "meta";
        }
        if (normalized.equals("AndroidManifest.xml")) {
            return "manifest";
        }
        if (normalized.equals("resources.arsc")) {
            return "resources";
        }
        return "other";
    }

    public static ApkAnalysis analyze(String path) {
        return analyze(path, null, true);
    }

    public static ApkAnalysis analyze(String path, Mapping mapping) {
        return analyze(path, mapping, true);
    }

    /**
     * Read an APK and build the class / resource inventory.
     *
     * @param hashContent when false, entry SHA-256 values are left empty (faster, but resource
     *                    change detection then relies only on size).
     */
    public static ApkAnalysis analyze(String path, Mapping mapping, boolean hashContent) {
        ApkAnalysis result = new ApkAnalysis(path, 0);
        try {
            result.setFileSize(Files.size(Paths.get(path)));
        } catch (IOException | RuntimeException ignored) {
            // Keep file size 0 when stat fails; the open error below will be reported.
        }

        ZipFile zip;
        try {
            zip = new ZipFile(path);
        } catch (IOException | RuntimeException exc) {
            result.getWarnings().add("cannot open APK: " + exc.getMessage());
            return result;
        }

        try (ZipFile zf = zip) {
            Map<String, byte[]> dexContents = new HashMap<>();
            java.util.Enumeration<? extends ZipEntry> entries = zf.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) {
                    continue;
                }
                String name = entry.getName().replace('\\', '/');
                String category = categorize(name);
                String digest = "";
                if (hashContent) {
                    try {
                        if (category.equals("dex")) {
                            // Read the dex once: hashing and analysis both need it.
                            byte[] content;
                            try (InputStream input = zf.getInputStream(entry)) {
                                content = input.readAllBytes();
                            }
                            digest = Util.sha256Hex(content);
                            dexContents.put(name, content);
                        } else {
                            try (InputStream input = zf.getInputStream(entry)) {
                                MessageDigest hasher = MessageDigest.getInstance("SHA-256");
                                byte[] buffer = new byte[1 << 20];
                                while (true) {
                                    int read = input.read(buffer);
                                    if (read < 0) {
                                        break;
                                    }
                                    if (read > 0) {
                                        hasher.update(buffer, 0, read);
                                    }
                                }
                                digest = Util.toHex(hasher.digest());
                            }
                        }
                    } catch (IOException | RuntimeException exc) {
                        result.getWarnings().add("cannot hash " + name + ": " + exc.getMessage());
                    } catch (NoSuchAlgorithmException exc) {
                        throw new IllegalStateException("SHA-256 unavailable", exc);
                    }
                }
                result.getEntries().put(name, new ApkEntry(
                        name,
                        category,
                        entry.getCompressedSize(),
                        entry.getSize(),
                        entry.getCrc(),
                        digest));
            }

            // Analyse every classes*.dex
            List<String> dexNames = new ArrayList<>();
            for (ApkEntry entry : result.getEntries().values()) {
                if (entry.getCategory().equals("dex")) {
                    dexNames.add(entry.getName());
                }
            }
            dexNames.sort((a, b) -> {
                int byOrder = Integer.compare(dexOrder(a), dexOrder(b));
                return byOrder != 0 ? byOrder : a.compareTo(b);
            });

            for (String dexName : dexNames) {
                DexAnalysis analysis;
                try {
                    byte[] raw = dexContents.get(dexName);
                    if (raw == null) {
                        try (InputStream input = zf.getInputStream(zf.getEntry(dexName))) {
                            raw = input.readAllBytes();
                        }
                    }
                    analysis = new DexFile(raw, dexName).analyze();
                } catch (IOException | RuntimeException exc) {
                    result.getWarnings().add("cannot analyze " + dexName + ": " + exc.getMessage());
                    continue;
                }
                result.getDexFiles().add(analysis);
                for (String warning : analysis.getWarnings()) {
                    result.getWarnings().add(dexName + ": " + warning);
                }

                ApkEntry entry = result.getEntries().get(dexName);
                if (entry == null) {
                    continue;
                }
                // Compressed size is an estimate: apply the dex-wide compression ratio to each
                // class's uncompressed size.
                double ratio = entry.getFileSize() != 0
                        ? (double) entry.getCompressSize() / (double) entry.getFileSize()
                        : 0.0;
                for (DexClass cls : analysis.getClasses()) {
                    String displayName = mapping != null
                            ? mapping.deobfuscateDescriptor(cls.getName())
                            : DexFile.descriptorToClassName(cls.getName());
                    long estimatedCompressed = Math.round(cls.getSize() * ratio);
                    ApkClass existing = result.getClasses().get(displayName);
                    if (existing != null) {
                        // The same class appearing in multiple dex files is rare but
                        // possible: conservatively sum the sizes and combine hashes so it
                        // cannot silently disappear.
                        existing.setSize(existing.getSize() + cls.getSize());
                        existing.setCompressedSize(existing.getCompressedSize() + estimatedCompressed);
                        existing.setBreakdown(existing.getBreakdown().plus(cls.getBreakdown()));
                        existing.setContentHash(Util.sha256Hex(
                                (existing.getContentHash() + cls.getContentHash())
                                        .getBytes(StandardCharsets.US_ASCII)));
                        existing.setPartial(existing.isPartial() || cls.isPartial());
                        existing.setWarning(Util.joinNonEmpty(existing.getWarning(), cls.getWarning()));
                    } else {
                        result.getClasses().put(displayName, new ApkClass(
                                displayName,
                                DexFile.descriptorToClassName(cls.getName()),
                                dexName,
                                cls.getSize(),
                                estimatedCompressed,
                                cls.getBreakdown(),
                                cls.getContentHash(),
                                cls.getMethods(),
                                cls.getFields(),
                                cls.isPartial(),
                                cls.getWarning()));
                    }
                }
            }
        } catch (IOException exc) {
            result.getWarnings().add("cannot read APK: " + exc.getMessage());
        }
        return result;
    }

    private static int dexOrder(String name) {
        String base = name.substring(name.lastIndexOf('/') + 1);
        if (base.equalsIgnoreCase("classes.dex")) {
            return 0;
        }
        Matcher match = DEX_NUMBER_RE.matcher(base);
        if (match.matches()) {
            try {
                return Integer.parseInt(match.group(1));
            } catch (NumberFormatException ignored) {
                return 9999;
            }
        }
        return 9999;
    }
}
