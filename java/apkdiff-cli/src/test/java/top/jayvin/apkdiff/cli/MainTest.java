package top.jayvin.apkdiff.cli;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MainTest {
    private static final Path FIXTURES = Paths.get(
            System.getProperty("apkdiff.fixtures") != null
                    ? System.getProperty("apkdiff.fixtures")
                    : "tests/fixtures");
    private static final Path V1 = FIXTURES.resolve("v1/v1.apk");
    private static final Path V2 = FIXTURES.resolve("v2/v2.apk");
    private static final Path C_V1 = FIXTURES.resolve("complex/v1/v1.apk");
    private static final Path C_V2 = FIXTURES.resolve("complex/v2/v2.apk");

    private static final class Capture {
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        final PrintStream stream = new PrintStream(buffer, true, StandardCharsets.UTF_8);

        String text() {
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }

    @Test
    void jsonHtmlMarkdownAndConsoleOutput() throws IOException {
        Assumptions.assumeTrue(Files.exists(V1) && Files.exists(V2), "fixtures missing");
        Path tmp = Files.createTempDirectory("apkdiff-cli");
        try {
            Capture stdout = new Capture();
            Capture stderr = new Capture();
            int code = Main.runCli(new String[]{
                    V1.toString(), V2.toString(),
                    "--format", "json,html,markdown,console",
                    "-o", tmp.toString(),
            }, stdout.stream, stderr.stream);
            assertEquals(0, code, stderr.text());

            JsonObject data = JsonParser.parseString(
                    Files.readString(tmp.resolve("apkdiff.json"), StandardCharsets.UTF_8))
                    .getAsJsonObject();
            JsonObject summary = data.getAsJsonObject("summary");
            assertEquals(1, summary.get("class_added").getAsInt());
            assertEquals(1, summary.get("class_deleted").getAsInt());
            assertEquals(1, summary.get("class_modified").getAsInt());

            String htmlText = Files.readString(tmp.resolve("apkdiff.html"), StandardCharsets.UTF_8);
            assertTrue(htmlText.contains("com.example.Alpha"));
            assertTrue(htmlText.contains("APK Diff Report"));
            assertTrue(Files.exists(tmp.resolve("apkdiff.md")));
            assertTrue(stdout.text().contains("APK DIFF REPORT"));
        } finally {
            deleteRecursively(tmp);
        }
    }

    @Test
    void failOnRegressionReturnsOneWhenNewApkIsLarger() throws IOException {
        Assumptions.assumeTrue(Files.exists(C_V1) && Files.exists(C_V2), "complex fixtures missing");
        Path tmp = Files.createTempDirectory("apkdiff-regression");
        try {
            Capture stdout = new Capture();
            int code = Main.runCli(new String[]{
                    C_V1.toString(), C_V2.toString(),
                    "--format", "json",
                    "--fail-on-regression",
                    "-o", tmp.toString(),
            }, stdout.stream, new PrintStream(new ByteArrayOutputStream()));
            assertEquals(1, code);
        } finally {
            deleteRecursively(tmp);
        }
    }

    @Test
    void missingApkIsAnError() {
        Capture stdout = new Capture();
        Capture stderr = new Capture();
        int code = Main.runCli(
                new String[]{"does-not-exist.apk", "also-missing.apk"},
                stdout.stream, stderr.stream);
        assertEquals(2, code);
        assertTrue(stderr.text().contains("APK 不存在"));
    }

    @Test
    void helpExitsZero() {
        Capture stdout = new Capture();
        int code = Main.runCli(new String[]{"--help"},
                stdout.stream, new PrintStream(new ByteArrayOutputStream()));
        assertEquals(0, code);
        assertTrue(stdout.text().contains("usage: apkdiff"));
    }

    @Test
    void invalidFormatIsRejected() {
        Capture stderr = new Capture();
        int code = Main.runCli(
                new String[]{V1.toString(), V2.toString(), "--format", "xml"},
                new PrintStream(new ByteArrayOutputStream()), stderr.stream);
        assertEquals(2, code);
        assertTrue(stderr.text().contains("不支持的输出格式"));
    }

    private static void deleteRecursively(Path path) throws IOException {
        if (!Files.exists(path)) {
            return;
        }
        try (var stream = Files.walk(path)) {
            stream.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException exc) {
                    throw new RuntimeException(exc);
                }
            });
        }
    }
}
