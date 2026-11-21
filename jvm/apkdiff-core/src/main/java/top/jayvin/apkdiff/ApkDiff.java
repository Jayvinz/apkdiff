package top.jayvin.apkdiff;

import java.io.PrintStream;
import java.util.LinkedHashMap;

/**
 * Static facade for the apkdiff library.
 *
 * <pre>{@code
 * Mapping oldMapping = ApkDiff.mapping("old/mapping.txt");
 * Mapping newMapping = ApkDiff.mapping("new/mapping.txt");
 * ApkAnalysis oldApk = ApkDiff.analyze("old.apk", oldMapping);
 * ApkAnalysis newApk = ApkDiff.analyze("new.apk", newMapping);
 *
 * DiffResult result = ApkDiff.diff(oldApk, newApk, false, true);
 * System.out.println(ApkDiff.sizeDelta(result.summaryLong("apk_size_delta")));
 * ApkDiff.writeJsonReport(result, "report/apkdiff.json", "compressed");
 * }</pre>
 */
public final class ApkDiff {
    private ApkDiff() {
    }

    /** Load a ProGuard/R8 mapping; returns an empty mapping when {@code path} is null. */
    public static Mapping mapping(String path) {
        return Mapping.load(path);
    }

    public static ApkAnalysis analyze(String apkPath) {
        return ApkAnalyzer.analyze(apkPath);
    }

    public static ApkAnalysis analyze(String apkPath, Mapping mapping) {
        return ApkAnalyzer.analyze(apkPath, mapping);
    }

    public static ApkAnalysis analyze(String apkPath, Mapping mapping, boolean hashContent) {
        return ApkAnalyzer.analyze(apkPath, mapping, hashContent);
    }

    public static DiffResult diff(ApkAnalysis old, ApkAnalysis newApk) {
        return Differ.diff(old, newApk);
    }

    public static DiffResult diff(ApkAnalysis old, ApkAnalysis newApk, boolean includeMeta) {
        return Differ.diff(old, newApk, includeMeta);
    }

    public static DiffResult diff(
            ApkAnalysis old,
            ApkAnalysis newApk,
            boolean includeMeta,
            boolean detectRenames) {
        return Differ.diff(old, newApk, includeMeta, detectRenames);
    }

    public static void printReport(DiffResult result) {
        Reporter.printConsole(result);
    }

    public static void printReport(DiffResult result, String metric) {
        Reporter.printConsole(result, metric);
    }

    public static void printReport(DiffResult result, String metric, int top, boolean full) {
        Reporter.printConsole(result, metric, top, full);
    }

    public static void printReport(
            DiffResult result,
            String metric,
            int top,
            boolean full,
            PrintStream out) {
        Reporter.printConsole(result, metric, top, full, out);
    }

    public static LinkedHashMap<String, Object> json(DiffResult result, String metric) {
        return Reporter.buildJson(result, metric);
    }

    public static void writeJsonReport(DiffResult result, String path, String metric) {
        Reporter.writeJson(result, path, metric);
    }

    public static void writeHtmlReport(DiffResult result, String path, String metric) {
        Reporter.writeHtml(result, path, metric);
    }

    public static void writeMarkdownReport(DiffResult result, String path, String metric) {
        Reporter.writeMarkdown(result, path, metric);
    }

    /** Human readable size in KB/MB/GB, e.g. "7.50 KB". */
    public static String size(Long bytes) {
        return Util.humanSize(bytes);
    }

    /** Signed human readable size change, e.g. "+7.50 KB" / "-0.25 KB". */
    public static String sizeDelta(Long bytes) {
        return Util.humanDelta(bytes);
    }
}
