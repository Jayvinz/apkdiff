package top.jayvin.apkdiff;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * End-to-end and unit tests for the pure Java implementation.
 *
 * <p>The fixture APKs in {@code tests/fixtures} were produced with the real Android toolchain
 * (javac + d8 + aapt), so these tests exercise real dex / zip data rather than hand-made
 * structures.</p>
 */
final class Fixtures {
    static final Path ROOT = Paths.get(
            System.getProperty("apkdiff.fixtures") != null
                    ? System.getProperty("apkdiff.fixtures")
                    : "tests/fixtures");
    static final Path V1 = ROOT.resolve("v1/v1.apk");
    static final Path V2 = ROOT.resolve("v2/v2.apk");
    static final Path COMPLEX = ROOT.resolve("complex");
    static final Path C_V1 = COMPLEX.resolve("v1/v1.apk");
    static final Path C_V2 = COMPLEX.resolve("v2/v2.apk");
    static final Path C_MANIFEST = COMPLEX.resolve("expected.json");

    private Fixtures() {
    }

    static void requireSmall() {
        Assumptions.assumeTrue(
                Files.exists(V1) && Files.exists(V2),
                "run tests/make_fixtures.py first");
    }

    static void requireComplex() {
        Assumptions.assumeTrue(
                Files.exists(C_V1) && Files.exists(C_V2) && Files.exists(C_MANIFEST),
                "run tests/make_complex_fixture.py first");
    }

    static ApkAnalysis analyze(Path apk) {
        Path mappingPath = apk.getParent().resolve("mapping.txt");
        Mapping mapping = Files.exists(mappingPath) ? Mapping.parse(mappingPath.toString()) : null;
        return ApkAnalyzer.analyze(apk.toString(), mapping);
    }

    static Map<String, String> statuses(List<Change> changes) {
        Map<String, String> out = new LinkedHashMap<>();
        for (Change change : changes) {
            out.put(change.getKey(), change.getStatus());
        }
        return out;
    }

    static void assertArrayEqualsInts(int[] expected, int[] actual) {
        assertEquals(expected.length, actual.length);
        for (int i = 0; i < expected.length; i++) {
            assertEquals(expected[i], actual[i]);
        }
    }
}

class SmallFixtureTest {
    @BeforeEach
    void setUp() {
        Fixtures.requireSmall();
    }

    @Test
    void classChanges() {
        DiffResult result = Differ.diff(Fixtures.analyze(Fixtures.V1), Fixtures.analyze(Fixtures.V2));
        Map<String, String> statuses = Fixtures.statuses(result.getClasses());
        Map<String, String> expected = new LinkedHashMap<>();
        expected.put("com.example.Alpha", DiffStatus.MODIFIED);
        expected.put("com.example.Gamma", DiffStatus.DELETED);
        expected.put("com.example.Delta", DiffStatus.ADDED);
        assertEquals(expected, statuses);
    }

    @Test
    void resourceChanges() {
        DiffResult result = Differ.diff(Fixtures.analyze(Fixtures.V1), Fixtures.analyze(Fixtures.V2));
        Map<String, String> statuses = Fixtures.statuses(result.getResources());
        assertEquals(DiffStatus.ADDED, statuses.get("res/raw/extra.txt"));
        assertEquals(DiffStatus.MODIFIED, statuses.get("assets/config.json"));
        assertEquals(DiffStatus.MODIFIED, statuses.get("resources.arsc"));
    }

    @Test
    void identicalApksHaveNoChanges() {
        ApkAnalysis analysis = Fixtures.analyze(Fixtures.V1);
        DiffResult result = Differ.diff(analysis, analysis);
        assertTrue(result.getClasses().isEmpty());
        assertTrue(result.getResources().isEmpty());
    }

    @Test
    void dexBytesAreFullyAccounted() {
        for (Path apk : new Path[]{Fixtures.V1, Fixtures.V2}) {
            ApkAnalysis analysis = Fixtures.analyze(apk);
            long dexTotal = 0;
            for (DexAnalysis dex : analysis.getDexFiles()) {
                dexTotal += dex.getFileSize();
            }
            assertEquals(dexTotal, analysis.totalClassBytes() + analysis.unattributedDexBytes());
        }
    }

    @Test
    void mappingDeobfuscation() {
        ApkAnalysis analysis = Fixtures.analyze(Fixtures.V1);
        assertTrue(analysis.getClasses().containsKey("com.example.Alpha"));
        assertFalse(analysis.getClasses().containsKey("p.a"));
    }
}

class ComplexFixtureTest {
    private JsonObject exp;

    @BeforeEach
    void setUp() throws IOException {
        Fixtures.requireComplex();
        exp = JsonParser.parseString(
                Files.readString(Fixtures.C_MANIFEST, StandardCharsets.UTF_8)).getAsJsonObject();
    }

    private Set<String> expectedSet(String section, String label) {
        Set<String> out = new LinkedHashSet<>();
        for (var item : exp.getAsJsonObject(section).getAsJsonArray(label)) {
            out.add(item.getAsString());
        }
        return out;
    }

    private ApkAnalysis analyzeComplex(Path apk) {
        return ApkAnalyzer.analyze(
                apk.toString(),
                Mapping.parse(apk.getParent().resolve("mapping.txt").toString()));
    }

    @Test
    void multidexAndNoParseWarnings() {
        for (Path apk : new Path[]{Fixtures.C_V1, Fixtures.C_V2}) {
            ApkAnalysis analysis = analyzeComplex(apk);
            List<String> dexFiles = new ArrayList<>();
            for (var item : exp.getAsJsonArray("dex_files")) {
                dexFiles.add(item.getAsString());
            }
            List<String> actualDexFiles = new ArrayList<>();
            for (DexAnalysis dex : analysis.getDexFiles()) {
                actualDexFiles.add(dex.getPath());
            }
            assertEquals(dexFiles, actualDexFiles);
            assertTrue(analysis.getWarnings().isEmpty(),
                    "warnings: " + analysis.getWarnings());
            for (Map.Entry<String, ApkClass> entry : analysis.getClasses().entrySet()) {
                assertEquals("", entry.getValue().getWarning(),
                        entry.getKey() + ": " + entry.getValue().getWarning());
                assertFalse(entry.getValue().isPartial(), entry.getKey() + ": partial parse");
            }
            long dexTotal = 0;
            for (DexAnalysis dex : analysis.getDexFiles()) {
                dexTotal += dex.getFileSize();
            }
            assertEquals(dexTotal, analysis.totalClassBytes() + analysis.unattributedDexBytes());
        }
    }

    @Test
    void businessClassChangesMatchManifest() {
        DiffResult result = Differ.diff(analyzeComplex(Fixtures.C_V1), analyzeComplex(Fixtures.C_V2));
        Map<String, String> statuses = Fixtures.statuses(result.getClasses());
        for (String[] pair : new String[][]{
                {DiffStatus.ADDED, "added"}, {DiffStatus.DELETED, "deleted"},
                {DiffStatus.MODIFIED, "modified"}}) {
            Set<String> actual = new LinkedHashSet<>();
            for (Map.Entry<String, String> entry : statuses.entrySet()) {
                if (entry.getKey().startsWith("com.shop.") && entry.getValue().equals(pair[0])) {
                    actual.add(entry.getKey());
                }
            }
            assertEquals(expectedSet("classes", pair[1]), actual);
        }
        // A large set of unrelated classes stays unchanged even though the DEX index pools
        // were reshuffled by the added/removed classes.
        assertFalse(statuses.containsKey("com.shop.ui.ProductListActivity"));
        assertFalse(statuses.containsKey("com.shop.ui.ProductDetailActivity"));
        assertFalse(statuses.containsKey("com.shop.util.Logger")); // annotation parse regression
    }

    @Test
    void syntheticAndInnerClassesArePresent() {
        ApkAnalysis analysis = analyzeComplex(Fixtures.C_V1);
        int synthetic = 0;
        for (String name : analysis.getClasses().keySet()) {
            if (name.contains("$")) {
                synthetic++;
            }
        }
        assertTrue(synthetic > 10, "inner/synthetic classes missing or too few");
        DiffResult result = Differ.diff(analyzeComplex(Fixtures.C_V1), analyzeComplex(Fixtures.C_V2));
        boolean hasAddedSynthetic = false;
        boolean hasDeletedSynthetic = false;
        for (Change change : result.getClasses()) {
            if (change.getKey().contains("$") && change.getStatus().equals(DiffStatus.ADDED)) {
                hasAddedSynthetic = true;
            }
            if (change.getKey().contains("$") && change.getStatus().equals(DiffStatus.DELETED)) {
                hasDeletedSynthetic = true;
            }
        }
        assertTrue(hasAddedSynthetic);
        assertTrue(hasDeletedSynthetic);
    }

    @Test
    void resourceChangesMatchManifest() {
        DiffResult result = Differ.diff(
                analyzeComplex(Fixtures.C_V1), analyzeComplex(Fixtures.C_V2), false, true);
        Map<String, String> statuses = Fixtures.statuses(result.getResources());
        for (String[] pair : new String[][]{
                {DiffStatus.ADDED, "added"}, {DiffStatus.DELETED, "deleted"},
                {DiffStatus.MODIFIED, "modified"}, {DiffStatus.RENAMED, "renamed"}}) {
            Set<String> actual = new LinkedHashSet<>();
            for (Map.Entry<String, String> entry : statuses.entrySet()) {
                if (entry.getValue().equals(pair[0])) {
                    actual.add(entry.getKey());
                }
            }
            assertEquals(expectedSet("resources", pair[1]), actual);
        }
        assertFalse(statuses.containsKey("res/raw/config.json"));
    }

    @Test
    void resourceTypesAreCovered() {
        ApkAnalysis analysis = analyzeComplex(Fixtures.C_V1);
        Set<String> names = analysis.getEntries().keySet();
        for (String suffix : new String[]{".xml", ".png", ".svg", ".db", ".so", ".json", ".bin"}) {
            assertTrue(names.stream().anyMatch(name -> name.endsWith(suffix)),
                    "fixture has no " + suffix + " entry");
        }
        for (String prefix : new String[]{"res/", "assets/", "lib/"}) {
            assertTrue(names.stream().anyMatch(name -> name.startsWith(prefix)), prefix);
        }
        assertTrue(names.contains("resources.arsc"));

        DiffResult result = Differ.diff(
                analyzeComplex(Fixtures.C_V1), analyzeComplex(Fixtures.C_V2), false, true);
        Map<String, String> statuses = Fixtures.statuses(result.getResources());
        assertEquals(DiffStatus.MODIFIED, statuses.get("assets/databases/app.db"));
        assertEquals(DiffStatus.ADDED, statuses.get("assets/databases/explore.db"));
        assertEquals(DiffStatus.MODIFIED, statuses.get("assets/images/hero.svg"));
        assertEquals(DiffStatus.ADDED, statuses.get("assets/images/explore.svg"));
        assertEquals(DiffStatus.DELETED, statuses.get("assets/images/legacy.svg"));
        assertEquals(DiffStatus.MODIFIED, statuses.get("res/raw/logo.svg"));
        assertEquals(DiffStatus.MODIFIED, statuses.get("res/mipmap-xxhdpi-v4/ic_launcher.png"));
    }

    @Test
    void metaFilesAreOptIn() {
        ApkAnalysis old = analyzeComplex(Fixtures.C_V1);
        ApkAnalysis latest = analyzeComplex(Fixtures.C_V2);
        DiffResult defaultResult = Differ.diff(old, latest);
        for (Change change : defaultResult.getResources()) {
            assertFalse(change.getKey().startsWith("META-INF"));
        }
        DiffResult withMeta = Differ.diff(old, latest, true, false);
        Map<String, String> meta = new LinkedHashMap<>();
        for (Change change : withMeta.getResources()) {
            if (change.getKey().startsWith("META-INF")) {
                meta.put(change.getKey(), change.getStatus());
            }
        }
        assertEquals(DiffStatus.MODIFIED, meta.get("META-INF/MANIFEST.MF"));
        assertEquals(DiffStatus.MODIFIED, meta.get("META-INF/CERT.SF"));
    }

    @Test
    void businessClassCountsMatchManifest() {
        // expected.json counts deobfuscated business classes (com.shop.*); the analysis
        // additionally contains D8-generated synthetic classes that have no mapping entry.
        JsonObject counts = exp.getAsJsonObject("class_count");
        int v1Business = 0;
        for (String name : analyzeComplex(Fixtures.C_V1).getClasses().keySet()) {
            if (name.startsWith("com.shop.")) {
                v1Business++;
            }
        }
        int v2Business = 0;
        for (String name : analyzeComplex(Fixtures.C_V2).getClasses().keySet()) {
            if (name.startsWith("com.shop.")) {
                v2Business++;
            }
        }
        assertEquals(counts.get("v1").getAsInt(), v1Business);
        assertEquals(counts.get("v2").getAsInt(), v2Business);
    }
}

class HelperTest {
    @Test
    void uleb128() {
        Fixtures.assertArrayEqualsInts(new int[]{0, 1}, DexFile.uleb128(new byte[]{0}, 0));
        Fixtures.assertArrayEqualsInts(
                new int[]{65537, 3},
                DexFile.uleb128(new byte[]{(byte) 0x81, (byte) 0x80, 0x04}, 0));
    }

    @Test
    void mappingParse() {
        Mapping mapping = Mapping.parse(Fixtures.ROOT.resolve("v1/mapping.txt").toString());
        assertEquals("com.example.Alpha", mapping.originalName("p.a"));
        assertEquals("com.example.Beta", mapping.deobfuscateDescriptor("Lp/b;"));
        assertEquals("unknown.X", mapping.originalName("unknown.X"));
    }

    @Test
    void categorizeEntries() {
        assertEquals("dex", ApkAnalyzer.categorize("classes2.dex"));
        assertEquals("res", ApkAnalyzer.categorize("res/drawable/icon.png"));
        assertEquals("assets", ApkAnalyzer.categorize("assets/data.json"));
        assertEquals("lib", ApkAnalyzer.categorize("lib/arm64-v8a/libx.so"));
        assertEquals("meta", ApkAnalyzer.categorize("META-INF/CERT.RSA"));
        assertEquals("resources", ApkAnalyzer.categorize("resources.arsc"));
    }

    @Test
    void emptyMappingIsHarmless() {
        Mapping mapping = Mapping.load(null);
        assertEquals("any.Class", mapping.originalName("any.Class"));
        assertNull(mapping.getClassNames().get("any.Class"));
    }
}
