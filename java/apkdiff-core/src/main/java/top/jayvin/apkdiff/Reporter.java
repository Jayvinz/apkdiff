package top.jayvin.apkdiff;

import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Renders the diff as console output, JSON, HTML, or Markdown.
 *
 * <p>All four formats share one data source ({@link DiffResult}) and one size-formatting
 * helper ({@link Util}), so the same number reads identically everywhere. JSON stores exact
 * integer byte counts; only human-facing output converts to KB with 2 decimals.</p>
 */
public final class Reporter {
    private Reporter() {
    }

    // ------------------------------------------------------------------
    // width helpers (terminal tables may contain Chinese labels)
    // ------------------------------------------------------------------

    private static boolean isWideCodePoint(int cp) {
        return (cp >= 0x1100 && cp <= 0x115F)
                || (cp >= 0x2329 && cp <= 0x232A)
                || (cp >= 0x2E80 && cp <= 0xA4CF && cp != 0x303F)
                || (cp >= 0xAC00 && cp <= 0xD7A3)
                || (cp >= 0xF900 && cp <= 0xFAFF)
                || (cp >= 0xFE10 && cp <= 0xFE19)
                || (cp >= 0xFE30 && cp <= 0xFE6F)
                || (cp >= 0xFF00 && cp <= 0xFF60)
                || (cp >= 0xFFE0 && cp <= 0xFFE6)
                || (cp >= 0x1F300 && cp <= 0x1F64F)
                || (cp >= 0x1F900 && cp <= 0x1F9FF)
                || (cp >= 0x20000 && cp <= 0x3FFFD);
    }

    private static int displayWidth(String text) {
        int width = 0;
        int i = 0;
        while (i < text.length()) {
            int cp = text.codePointAt(i);
            width += isWideCodePoint(cp) ? 2 : 1;
            i += Character.charCount(cp);
        }
        return width;
    }

    private static String pad(String text, int width) {
        return text + " ".repeat(Math.max(0, width - displayWidth(text)));
    }

    private static String padChars(String text, int width) {
        return text + " ".repeat(Math.max(0, width - text.length()));
    }

    private static String padStart(long value, int width) {
        String text = Long.toString(value);
        int padding = Math.max(0, width - text.length());
        return " ".repeat(padding) + text;
    }

    private static List<Change> byImpact(List<Change> changes, String metric) {
        List<Change> sorted = new ArrayList<>(changes);
        sorted.sort(java.util.Comparator
                .comparingLong((Change change) -> Math.abs(change.sizeFor(metric))
                ).reversed());
        return sorted;
    }

    private static String statusMark(String status) {
        switch (status) {
            case DiffStatus.ADDED:
                return "+";
            case DiffStatus.DELETED:
                return "-";
            case DiffStatus.MODIFIED:
                return "~";
            case DiffStatus.RENAMED:
                return ">";
            default:
                return "?";
        }
    }

    private static String metricUnit(String metric) {
        return metric.equals("compressed") ? "APK 压缩字节" : "未压缩字节";
    }

    // ------------------------------------------------------------------
    // console
    // ------------------------------------------------------------------

    private static void printTable(
            String title,
            List<Change> changes,
            String metric,
            int limit,
            PrintStream out) {
        out.println();
        out.println(title + "  (共 " + changes.size() + " 项，显示前 " + Math.min(limit, changes.size()) + " 项)");
        if (changes.isEmpty()) {
            out.println("  （无）");
            return;
        }
        List<Change> shown = byImpact(changes, metric);
        if (!shown.isEmpty() && limit < shown.size()) {
            shown = shown.subList(0, Math.max(0, limit));
        }
        int nameW = 0;
        for (Change change : shown) {
            nameW = Math.max(nameW, displayWidth(change.getKey()));
        }
        nameW = Math.min(72, nameW);
        nameW = Math.max(nameW, 12);
        int oldW = 11;
        int newW = 11;
        int deltaW = 13;
        String header = "  " + padChars("", 2) + " " + padChars("状态", 6) + " "
                + pad("名称", nameW) + " " + pad("旧", oldW) + " " + pad("新", newW)
                + " " + pad("Δ", deltaW);
        out.println(header);
        out.println("  " + "-".repeat(header.length() - 2));
        for (Change c : shown) {
            String name = c.getKey();
            if (displayWidth(name) > nameW) {
                name = name.substring(0, Math.max(0, nameW - 3)) + "...";
            }
            long old = c.oldFor(metric);
            long newValue = c.newFor(metric);
            long delta = c.sizeFor(metric);
            out.println("  " + statusMark(c.getStatus()) + "  "
                    + pad(DiffStatus.label(c.getStatus()), 6) + " "
                    + pad(name, nameW) + " " + pad(Util.humanSize(old), oldW) + " "
                    + pad(Util.humanSize(newValue), newW) + " "
                    + pad(Util.humanDelta(delta), deltaW));
            if (c.getStatus().equals(DiffStatus.RENAMED) && c.getDetail().get("renamed_from") != null) {
                out.println("       └─ 原路径: " + c.getDetail().get("renamed_from"));
            }
            Object deltaObject = c.getDetail().get("breakdown_delta");
            if (deltaObject instanceof Map) {
                List<String> parts = new ArrayList<>();
                for (Map.Entry<?, ?> entry : ((Map<?, ?>) deltaObject).entrySet()) {
                    Object value = entry.getValue();
                    if (value instanceof Number && ((Number) value).longValue() != 0L) {
                        parts.add(entry.getKey() + " "
                                + Util.humanDelta(((Number) value).longValue()));
                    }
                }
                if (!parts.isEmpty()) {
                    out.println("       └─ 明细: " + String.join(" ", parts));
                }
            }
        }
    }

    /** Print the console report to {@code out}. */
    public static void printConsole(DiffResult result) {
        printConsole(result, "compressed", 30, false, System.out);
    }

    public static void printConsole(DiffResult result, String metric) {
        printConsole(result, metric, 30, false, System.out);
    }

    public static void printConsole(DiffResult result, String metric, int top) {
        printConsole(result, metric, top, false, System.out);
    }

    public static void printConsole(DiffResult result, String metric, int top, boolean full) {
        printConsole(result, metric, top, full, System.out);
    }

    public static void printConsole(
            DiffResult result,
            String metric,
            int top,
            boolean full,
            PrintStream out) {
        int limit = full ? Integer.MAX_VALUE : Math.max(0, top);
        String unit = metricUnit(metric);

        out.println("=".repeat(78));
        out.println("APK DIFF REPORT");
        out.println("=".repeat(78));
        out.println("  旧版本: " + result.getOld().getPath());
        out.println("  新版本: " + result.getNew().getPath());
        out.println("  排序/主指标: " + unit);
        out.println();
        out.println("  ── 包体总览 ──");
        out.println("  APK 文件          " + Util.humanSize(result.summaryLong("old_apk_size"))
                + " → " + Util.humanSize(result.summaryLong("new_apk_size"))
                + "   Δ " + Util.humanDelta(result.summaryLong("apk_size_delta")));
        out.println("  代码(DEX,估算压缩) " + Util.humanSize(result.summaryLong("old_class_compressed"))
                + " → " + Util.humanSize(result.summaryLong("new_class_compressed"))
                + "   Δ " + Util.humanDelta(result.summaryLong("class_compressed_delta")));
        out.println("  代码(DEX,归属原始) " + Util.humanSize(result.summaryLong("old_class_bytes"))
                + " → " + Util.humanSize(result.summaryLong("new_class_bytes"))
                + "   Δ " + Util.humanDelta(result.summaryLong("class_bytes_delta")));
        out.println("  资源(压缩)        " + Util.humanSize(result.summaryLong("old_resource_compressed"))
                + " → " + Util.humanSize(result.summaryLong("new_resource_compressed"))
                + "   Δ " + Util.humanDelta(result.summaryLong("resource_compressed_delta")));
        out.println("  资源(原始)        " + Util.humanSize(result.summaryLong("old_resource_bytes"))
                + " → " + Util.humanSize(result.summaryLong("new_resource_bytes"))
                + "   Δ " + Util.humanDelta(result.summaryLong("resource_bytes_delta")));
        out.println();
        out.println("  ── 变更统计 ──");
        out.println("  类:   新增 " + padStart(result.summaryLong("class_added"), 4)
                + "  删除 " + padStart(result.summaryLong("class_deleted"), 4)
                + "  修改 " + padStart(result.summaryLong("class_modified"), 4)
                + "   (旧 " + result.summaryLong("class_count_old")
                + " → 新 " + result.summaryLong("class_count_new") + ")");
        out.println("  资源: 新增 " + padStart(result.summaryLong("resource_added"), 4)
                + "  删除 " + padStart(result.summaryLong("resource_deleted"), 4)
                + "  修改 " + padStart(result.summaryLong("resource_modified"), 4)
                + "  重命名 " + padStart(result.summaryLong("resource_renamed"), 4));

        printTable("代码类变更", result.getClasses(), metric, limit, out);
        printTable("资源文件变更", result.getResources(), metric, limit, out);

        List<String> warnings = new ArrayList<>(result.getOld().getWarnings());
        warnings.addAll(result.getNew().getWarnings());
        if (!warnings.isEmpty()) {
            out.println();
            out.println("  ⚠ 解析警告 " + warnings.size() + " 条:");
            for (int i = 0; i < Math.min(20, warnings.size()); i++) {
                out.println("    - " + warnings.get(i));
            }
            if (warnings.size() > 20) {
                out.println("    ... 另有 " + (warnings.size() - 20) + " 条");
            }
        }
    }

    // ------------------------------------------------------------------
    // JSON
    // ------------------------------------------------------------------

    /** Build the object written to {@code apkdiff.json}. */
    public static LinkedHashMap<String, Object> buildJson(DiffResult result, String metric) {
        LinkedHashMap<String, Object> oldInfo = new LinkedHashMap<>();
        oldInfo.put("path", result.getOld().getPath());
        oldInfo.put("file_size", result.getOld().getFileSize());
        oldInfo.put("warnings", result.getOld().getWarnings());

        LinkedHashMap<String, Object> newInfo = new LinkedHashMap<>();
        newInfo.put("path", result.getNew().getPath());
        newInfo.put("file_size", result.getNew().getFileSize());
        newInfo.put("warnings", result.getNew().getWarnings());

        List<Object> classes = new ArrayList<>();
        for (Change change : byImpact(result.getClasses(), metric)) {
            classes.add(change.asMap());
        }
        List<Object> resources = new ArrayList<>();
        for (Change change : byImpact(result.getResources(), metric)) {
            resources.add(change.asMap());
        }

        LinkedHashMap<String, Object> json = new LinkedHashMap<>();
        json.put("schema_version", 1);
        json.put("metric", metric);
        json.put("old", oldInfo);
        json.put("new", newInfo);
        json.put("summary", result.getSummary());
        json.put("classes", classes);
        json.put("resources", resources);
        return json;
    }

    public static void writeJson(DiffResult result, String path, String metric) {
        writeFile(path, JsonWriter.write(buildJson(result, metric)));
    }

    // ------------------------------------------------------------------
    // Markdown
    // ------------------------------------------------------------------

    public static void writeMarkdown(DiffResult result, String path, String metric) {
        LinkedHashMap<String, Object> summary = result.getSummary();
        List<String> lines = new ArrayList<>();
        lines.add("# APK Diff Report");
        lines.add("");
        lines.add("- 旧版本: `" + result.getOld().getPath() + "`");
        lines.add("- 新版本: `" + result.getNew().getPath() + "`");
        lines.add("- 主指标: " + metricUnit(metric));
        lines.add("");
        lines.add("## 总览");
        lines.add("");
        lines.add("| 指标 | 旧 | 新 | Δ |");
        lines.add("| --- | ---: | ---: | ---: |");
        String[][] rows = {
                {"APK 文件", "old_apk_size", "new_apk_size", "apk_size_delta"},
                {"代码 (DEX 归属, 原始)", "old_class_bytes", "new_class_bytes", "class_bytes_delta"},
                {"代码 (DEX 归属, 压缩估算)", "old_class_compressed", "new_class_compressed",
                        "class_compressed_delta"},
                {"资源 (原始)", "old_resource_bytes", "new_resource_bytes", "resource_bytes_delta"},
                {"资源 (压缩)", "old_resource_compressed", "new_resource_compressed",
                        "resource_compressed_delta"},
        };
        for (String[] row : rows) {
            lines.add("| " + row[0] + " | " + Util.humanSize(result.summaryLong(row[1])) + " | "
                    + Util.humanSize(result.summaryLong(row[2])) + " | "
                    + Util.humanDelta(result.summaryLong(row[3])) + " |");
        }
        lines.add("");
        lines.add("## 统计");
        lines.add("");
        lines.add("- 类: 新增 " + summary.get("class_added")
                + " / 删除 " + summary.get("class_deleted")
                + " / 修改 " + summary.get("class_modified"));
        lines.add("- 资源: 新增 " + summary.get("resource_added")
                + " / 删除 " + summary.get("resource_deleted")
                + " / 修改 " + summary.get("resource_modified")
                + " / 重命名 " + summary.get("resource_renamed"));
        lines.add("");
        appendMarkdownTable(lines, "代码类变更", result.getClasses(), metric);
        appendMarkdownTable(lines, "资源文件变更", result.getResources(), metric);
        writeFile(path, String.join("\n", lines));
    }

    private static void appendMarkdownTable(
            List<String> lines,
            String title,
            List<Change> changes,
            String metric) {
        lines.add("## " + title);
        lines.add("");
        if (changes.isEmpty()) {
            lines.add("（无）");
            return;
        }
        lines.add("| 状态 | 名称 | 旧 | 新 | Δ |");
        lines.add("| --- | --- | ---: | ---: | ---: |");
        for (Change c : byImpact(changes, metric)) {
            long old = c.oldFor(metric);
            long newValue = c.newFor(metric);
            String name = c.getKey().replace("|", "\\|");
            String extra = "";
            Object renamedFrom = c.getDetail().get("renamed_from");
            if (renamedFrom instanceof String) {
                extra = " ← `" + renamedFrom + "`";
            }
            lines.add("| " + DiffStatus.label(c.getStatus()) + " | `" + name + "`" + extra + " | "
                    + Util.humanSize(old) + " | " + Util.humanSize(newValue) + " | "
                    + Util.humanDelta(c.sizeFor(metric)) + " |");
        }
        lines.add("");
    }

    // ------------------------------------------------------------------
    // HTML
    // ------------------------------------------------------------------

    private static String escapeHtml(String text) {
        StringBuilder out = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '&':
                    out.append("&amp;");
                    break;
                case '<':
                    out.append("&lt;");
                    break;
                case '>':
                    out.append("&gt;");
                    break;
                case '"':
                    out.append("&quot;");
                    break;
                case '\'':
                    out.append("&#x27;");
                    break;
                default:
                    out.append(ch);
                    break;
            }
        }
        return out.toString();
    }

    private static final String HTML_TEMPLATE = loadTemplate();

    private static String loadTemplate() {
        try (InputStream input = Reporter.class.getResourceAsStream(
                "/top/jayvin/apkdiff/report-template.html")) {
            if (input == null) {
                throw new IllegalStateException("report-template.html is missing from the jar");
            }
            byte[] bytes = input.readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (IOException exc) {
            throw new UncheckedIOException(exc);
        }
    }

    private static String htmlRows(List<Change> changes, String metric) {
        if (changes.isEmpty()) {
            return "<tr><td colspan=\"6\" class=\"detail\">（无变更）</td></tr>";
        }
        long maxImpact = 1;
        for (Change change : changes) {
            maxImpact = Math.max(maxImpact, Math.abs(change.sizeFor(metric)));
        }
        StringBuilder parts = new StringBuilder();
        for (Change c : byImpact(changes, metric)) {
            long old = c.oldFor(metric);
            long newValue = c.newFor(metric);
            long delta = c.sizeFor(metric);
            String cls = delta > 0 ? "up" : (delta < 0 ? "down" : "flat");
            String barColor = delta > 0 ? "var(--red)" : "var(--green)";
            int width = Math.max(2,
                    (int) Math.round(Math.abs(delta) / (double) maxImpact * 100));
            List<String> detailParts = new ArrayList<>();
            Object renamedFrom = c.getDetail().get("renamed_from");
            if (renamedFrom instanceof String) {
                detailParts.add("原路径 " + escapeHtml((String) renamedFrom));
            }
            Object deltaObject = c.getDetail().get("breakdown_delta");
            if (deltaObject instanceof Map) {
                List<String> partsInner = new ArrayList<>();
                for (Map.Entry<?, ?> entry : ((Map<?, ?>) deltaObject).entrySet()) {
                    Object value = entry.getValue();
                    if (value instanceof Number && ((Number) value).longValue() != 0L) {
                        partsInner.add(entry.getKey() + " "
                                + Util.humanDelta(((Number) value).longValue()));
                    }
                }
                detailParts.add(String.join(" ", partsInner));
            }
            Object dex = c.getDetail().get("dex");
            if (dex instanceof String) {
                detailParts.add("dex: " + escapeHtml((String) dex));
            }
            String detail = String.join(" · ", detailParts);
            String detailHtml = detail.isEmpty()
                    ? "" : "<div class=\"detail\">" + detail + "</div>";
            parts.append("<tr data-status=\"").append(c.getStatus())
                    .append("\" data-search=\"")
                    .append(escapeHtml(c.getKey().toLowerCase(Locale.ROOT)))
                    .append("\">")
                    .append("<td><span class=\"tag ").append(c.getStatus()).append("\">")
                    .append(DiffStatus.label(c.getStatus())).append("</span></td>")
                    .append("<td><div class=\"name\">").append(escapeHtml(c.getKey()))
                    .append("</div>").append(detailHtml)
                    .append("<div class=\"bar\"><i style=\"width:").append(width)
                    .append("%;background:").append(barColor).append("\"></i></div></td>")
                    .append("<td class=\"num\" data-v=\"").append(old).append("\">")
                    .append(Util.humanSize(old)).append("</td>")
                    .append("<td class=\"num\" data-v=\"").append(newValue).append("\">")
                    .append(Util.humanSize(newValue)).append("</td>")
                    .append("<td class=\"num ").append(cls).append("\" data-v=\"").append(delta)
                    .append("\">").append(Util.humanDelta(delta)).append("</td>")
                    .append("<td class=\"num\" data-v=\"").append(Math.abs(delta)).append("\">")
                    .append(Util.humanSize(Math.abs(delta))).append("</td>")
                    .append("</tr>");
        }
        return parts.toString();
    }

    private static String htmlTable(
            String tableId,
            String title,
            List<Change> changes,
            String metric) {
        StringBuilder pills = new StringBuilder();
        String[] statuses = {DiffStatus.ADDED, DiffStatus.DELETED, DiffStatus.MODIFIED, DiffStatus.RENAMED};
        String[] labels = {"新增", "删除", "修改", "重命名"};
        pills.append("<span class=\"pill active\" data-pill-group=\"").append(tableId)
                .append("\" data-status=\"all\">全部 ").append(changes.size()).append("</span>");
        for (int i = 0; i < statuses.length; i++) {
            int count = 0;
            for (Change change : changes) {
                if (change.getStatus().equals(statuses[i])) {
                    count++;
                }
            }
            pills.append("<span class=\"pill \" data-pill-group=\"").append(tableId)
                    .append("\" data-status=\"").append(statuses[i]).append("\">")
                    .append(labels[i]).append(" ").append(count).append("</span>");
        }
        return "\n  <h2>" + title
                + " <span class=\"sub\" style=\"display:inline\">(" + changes.size() + " 项)</span></h2>\n"
                + "  <div class=\"panel\">\n"
                + "    <div class=\"toolbar\">\n"
                + "      <input id=\"q_" + tableId + "\" type=\"text\" placeholder=\"搜索类名 / 文件名…\">\n"
                + "      " + pills + "\n"
                + "    </div>\n"
                + "    <table id=\"" + tableId + "\">\n"
                + "      <thead><tr>\n"
                + "        <th data-sort>状态</th><th data-sort>名称</th>\n"
                + "        <th class=\"num\" data-sort>旧</th><th class=\"num\" data-sort>新</th>\n"
                + "        <th class=\"num\" data-sort>Δ</th><th class=\"num\" data-sort>Δ 大小</th>\n"
                + "      </tr></thead>\n"
                + "      <tbody>" + htmlRows(changes, metric) + "</tbody>\n"
                + "    </table>\n"
                + "  </div>";
    }

    public static void writeHtml(DiffResult result, String path, String metric) {
        String[][] cards = {
                {"APK 文件", "old_apk_size", "new_apk_size", "apk_size_delta"},
                {"代码 (压缩估算)", "old_class_compressed", "new_class_compressed",
                        "class_compressed_delta"},
                {"代码 (原始归属)", "old_class_bytes", "new_class_bytes", "class_bytes_delta"},
                {"资源 (压缩)", "old_resource_compressed", "new_resource_compressed",
                        "resource_compressed_delta"},
                {"资源 (原始)", "old_resource_bytes", "new_resource_bytes", "resource_bytes_delta"},
        };
        StringBuilder cardHtml = new StringBuilder();
        for (String[] card : cards) {
            String label = card[0];
            long old = result.summaryLong(card[1]);
            long newValue = result.summaryLong(card[2]);
            long delta = result.summaryLong(card[3]);
            String cls = delta > 0 ? "up" : (delta < 0 ? "down" : "flat");
            cardHtml.append("<div class=\"card\"><div class=\"label\">").append(label)
                    .append("</div><div class=\"value\">").append(Util.humanSize(newValue))
                    .append("</div><div class=\"delta ").append(cls).append("\">")
                    .append(Util.humanDelta(delta))
                    .append(" &nbsp;(旧 ").append(Util.humanSize(old)).append(")</div></div>");
        }

        List<String> warnings = new ArrayList<>(result.getOld().getWarnings());
        warnings.addAll(result.getNew().getWarnings());
        String warnHtml = "";
        if (!warnings.isEmpty()) {
            StringBuilder items = new StringBuilder();
            for (int i = 0; i < Math.min(50, warnings.size()); i++) {
                items.append("<li>").append(escapeHtml(warnings.get(i))).append("</li>");
            }
            warnHtml = "<div class=\"warn\"><b>解析警告 (" + warnings.size() + ")</b><ul>"
                    + items + "</ul></div>";
        }

        String body = HTML_TEMPLATE
                .replace("__OLD__", escapeHtml(result.getOld().getPath()))
                .replace("__NEW__", escapeHtml(result.getNew().getPath()))
                .replace("__METRIC__", metricUnit(metric))
                .replace("__CARDS__", cardHtml.toString())
                .replace("__CLASS_TABLE__", htmlTable("classes", "代码类变更", result.getClasses(), metric))
                .replace("__RES_TABLE__", htmlTable("resources", "资源文件变更", result.getResources(), metric))
                .replace("__WARNINGS__", warnHtml)
                .replace("__JS_BIND__",
                        "bindTable('q_classes','classes',document.querySelectorAll('[data-pill-group=classes]'));\n"
                                + "bindTable('q_resources','resources',document.querySelectorAll('[data-pill-group=resources]'));");

        writeFile(path, body);
    }

    // ------------------------------------------------------------------
    // file helper
    // ------------------------------------------------------------------

    private static void writeFile(String path, String content) {
        Path target = Paths.get(path);
        try {
            Path parent = target.toAbsolutePath().getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(target, content, StandardCharsets.UTF_8);
        } catch (IOException exc) {
            throw new UncheckedIOException(exc);
        }
    }
}
