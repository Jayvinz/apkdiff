package top.jayvin.apkdiff;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Reads a ProGuard / R8 {@code mapping.txt} and resolves obfuscated class names back to
 * business names. Only class-level mappings are parsed: method/field mappings are present in
 * the file but the report does not display them.
 *
 * <p>A missing mapping file is fine; names from the DEX are shown unchanged.</p>
 */
public class Mapping {
    private static final Pattern CLASS_RE =
            Pattern.compile("^\\s*(\\S+)\\s+->\\s+(\\S+):\\s*$");

    private final String path;
    private final LinkedHashMap<String, String> classNames;
    private final List<String> warnings;

    public Mapping(String path) {
        this(path, new LinkedHashMap<>(), new ArrayList<>());
    }

    public Mapping(
            String path,
            LinkedHashMap<String, String> classNames,
            List<String> warnings) {
        this.path = path;
        this.classNames = classNames;
        this.warnings = warnings;
    }

    public String getPath() {
        return path;
    }

    /** Obfuscated dotted name to original dotted name. */
    public LinkedHashMap<String, String> getClassNames() {
        return classNames;
    }

    public List<String> getWarnings() {
        return warnings;
    }

    /**
     * Resolve a dotted obfuscated class name, longest-prefix safe.
     * Falls back to the input when no mapping exists.
     */
    public String originalName(String obfuscated) {
        String name = obfuscated.trim();
        String mapped = classNames.get(name);
        if (mapped != null) {
            return mapped;
        }
        // Some R8 versions emit array-ish or generic suffixes; strip them.
        for (String suffix : new String[]{"[]", "..."}) {
            while (name.endsWith(suffix)) {
                name = name.substring(0, name.length() - suffix.length());
            }
        }
        mapped = classNames.get(name);
        return mapped != null ? mapped : obfuscated;
    }

    /** 'La/b/c;' to original fully-qualified class name. */
    public String deobfuscateDescriptor(String descriptor) {
        return originalName(DexFile.descriptorToClassName(descriptor));
    }

    public static Mapping parse(String path) {
        Mapping mapping = new Mapping(path);
        List<String> lines;
        try {
            lines = Files.readAllLines(Paths.get(path), StandardCharsets.UTF_8);
        } catch (IOException | RuntimeException exc) {
            mapping.warnings.add("cannot read mapping file: " + exc.getMessage());
            return mapping;
        }

        for (int index = 0; index < lines.size(); index++) {
            int lineno = index + 1;
            // Only class mappings match this shape:
            //   com.shop.ui.MainActivity -> a.b:
            // Comments and method/field lines are skipped.
            Matcher match = CLASS_RE.matcher(lines.get(index));
            if (!match.matches()) {
                continue;
            }
            String original = match.group(1);
            String obfuscated = match.group(2);
            if (original.startsWith("#") || obfuscated.startsWith("#")) {
                continue;
            }
            String previous = mapping.classNames.put(obfuscated, original);
            if (previous != null && !previous.equals(original)) {
                mapping.warnings.add(
                        "line " + lineno + ": duplicate obfuscated name '" + obfuscated + "'");
            }
        }
        return mapping;
    }

    /** Load a mapping file, returning an empty Mapping when {@code path} is null or blank. */
    public static Mapping load(String path) {
        if (path == null || path.trim().isEmpty()) {
            return new Mapping("");
        }
        return parse(path);
    }
}
