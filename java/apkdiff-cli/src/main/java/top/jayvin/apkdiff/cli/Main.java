package top.jayvin.apkdiff.cli;

import top.jayvin.apkdiff.ApkAnalysis;
import top.jayvin.apkdiff.ApkAnalyzer;
import top.jayvin.apkdiff.DiffResult;
import top.jayvin.apkdiff.Differ;
import top.jayvin.apkdiff.Mapping;
import top.jayvin.apkdiff.Reporter;

import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * Command line entry point.
 *
 * <p>Flow: parse arguments, analyse the old APK, analyse the new APK, diff, render reports.
 * {@code --fail-on-regression} makes the process exit 1 when the new APK is larger, which is
 * how a CI size gate works.</p>
 */
public final class Main {
    private static final List<String> VALID_FORMATS =
            Arrays.asList("console", "json", "html", "markdown");

    private Main() {
    }

    private static final class CliError extends RuntimeException {
        CliError(String message) {
            super(message);
        }
    }

    private static final class HelpRequested extends RuntimeException {
    }

    private static final class Options {
        String oldApk;
        String newApk;
        String oldMapping;
        String newMapping;
        String format = "console,json,html";
        String output = "apkdiff-report";
        String metric = "compressed";
        int top = 30;
        boolean full;
        boolean includeMeta;
        boolean detectRenames;
        boolean failOnRegression;
    }

    private static String usageText() {
        return String.join("\n", Arrays.asList(
                "usage: apkdiff [-h] [--old-mapping OLD_MAPPING] [--new-mapping NEW_MAPPING]",
                "               [--format FORMAT] [-o OUTPUT] [--metric {compressed,uncompressed}]",
                "               [--top TOP] [--full] [--include-meta] [--detect-renames]",
                "               [--fail-on-regression]",
                "               old_apk new_apk",
                "",
                "对比两个 APK，按类 / 资源粒度输出体积变更报告。",
                "",
                "positional arguments:",
                "  old_apk               旧版本 APK 路径",
                "  new_apk               新版本 APK 路径",
                "",
                "options:",
                "  -h, --help            显示帮助并退出",
                "  --old-mapping OLD_MAPPING",
                "                        旧版本 ProGuard/R8 mapping.txt（默认自动探测）",
                "  --new-mapping NEW_MAPPING",
                "                        新版本 ProGuard/R8 mapping.txt（默认自动探测）",
                "  --format FORMAT       输出格式，逗号分隔：console,json,html,markdown（默认 console,json,html）",
                "  -o, --output OUTPUT   报告输出目录（默认 apkdiff-report）",
                "  --metric {compressed,uncompressed}",
                "                        排序与 Δ 显示所用的指标（默认 compressed）",
                "  --top TOP             控制台每种类型显示条数（默认 30）",
                "  --full                控制台显示全部条目",
                "  --include-meta        把 META-INF 纳入资源对比",
                "  --detect-renames      检测内容相同的资源重命名",
                "  --fail-on-regression  若新 APK 体积增大则以退出码 1 结束（便于 CI 使用）"));
    }

    private static String requiredValue(String[] argv, int[] cursor, String flag) {
        int i = cursor[0];
        if (i + 1 >= argv.length) {
            throw new CliError("argument " + flag + ": expected one argument");
        }
        cursor[0] = i + 1;
        return argv[i + 1];
    }

    private static Options parseArgs(String[] argv) {
        Options options = new Options();
        List<String> positional = new ArrayList<>();
        int[] cursor = {0};

        while (cursor[0] < argv.length) {
            String arg = argv[cursor[0]];
            int eq = arg.startsWith("--") ? arg.indexOf('=') : -1;
            String name = eq >= 0 ? arg.substring(0, eq) : arg;
            String inlineValue = eq >= 0 ? arg.substring(eq + 1) : null;

            switch (name) {
                case "-h":
                case "--help":
                    throw new HelpRequested();
                case "--old-mapping":
                    options.oldMapping = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    break;
                case "--new-mapping":
                    options.newMapping = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    break;
                case "--format":
                    options.format = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    break;
                case "-o":
                case "--output":
                    options.output = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    break;
                case "--metric":
                    options.metric = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    break;
                case "--top": {
                    String raw = inlineValue != null
                            ? inlineValue : requiredValue(argv, cursor, name);
                    try {
                        options.top = Integer.parseInt(raw);
                    } catch (NumberFormatException exc) {
                        throw new CliError("argument --top: invalid int value: '" + raw + "'");
                    }
                    break;
                }
                case "--full":
                    options.full = true;
                    break;
                case "--include-meta":
                    options.includeMeta = true;
                    break;
                case "--detect-renames":
                    options.detectRenames = true;
                    break;
                case "--fail-on-regression":
                    options.failOnRegression = true;
                    break;
                default:
                    if (name.startsWith("-")) {
                        throw new CliError("unrecognized arguments: " + arg);
                    }
                    positional.add(arg);
                    break;
            }
            cursor[0]++;
        }

        if (positional.isEmpty()) {
            throw new CliError("the following arguments are required: old_apk, new_apk");
        }
        if (positional.size() == 1) {
            throw new CliError("the following arguments are required: new_apk");
        }
        if (positional.size() > 2) {
            throw new CliError("unrecognized arguments: "
                    + String.join(" ", positional.subList(2, positional.size())));
        }
        options.oldApk = positional.get(0);
        options.newApk = positional.get(1);
        return options;
    }

    /** Look for a mapping file next to the APK. */
    private static String autodetectMapping(String apkPath) {
        Path apk = Paths.get(apkPath).toAbsolutePath().normalize();
        String fileName = apk.getFileName().toString();
        int dot = fileName.lastIndexOf('.');
        String stem = dot > 0 ? fileName.substring(0, dot) : fileName;
        Path[] candidates = {
                apk.resolveSibling(stem + "-mapping.txt"),
                apk.resolveSibling(stem + ".mapping.txt"),
                apk.resolveSibling("mapping.txt"),
        };
        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate)) {
                return candidate.toString();
            }
        }
        return null;
    }

    /** Run the CLI. Returns the process exit code. */
    public static int runCli(String[] argv) {
        return runCli(argv, System.out, System.err);
    }

    public static int runCli(String[] argv, PrintStream out, PrintStream err) {
        Options options;
        try {
            options = parseArgs(argv);
        } catch (HelpRequested exc) {
            out.println(usageText());
            return 0;
        } catch (CliError exc) {
            err.println(usageText());
            err.println("apkdiff: error: " + exc.getMessage());
            return 2;
        }

        List<String> formats = new ArrayList<>();
        for (String part : options.format.split(",", -1)) {
            String format = part.trim().toLowerCase(Locale.ROOT);
            if (!format.isEmpty()) {
                formats.add(format);
            }
        }
        List<String> invalid = new ArrayList<>();
        for (String format : formats) {
            if (!VALID_FORMATS.contains(format)) {
                invalid.add(format);
            }
        }
        if (!invalid.isEmpty()) {
            err.println(usageText());
            err.println("apkdiff: error: 不支持的输出格式: " + String.join(", ", invalid)
                    + "；可选: " + String.join(", ", VALID_FORMATS));
            return 2;
        }
        if (!options.metric.equals("compressed") && !options.metric.equals("uncompressed")) {
            err.println(usageText());
            err.println("apkdiff: error: argument --metric: invalid choice: '" + options.metric + "'");
            return 2;
        }

        String oldApk = options.oldApk;
        String newApk = options.newApk;
        for (String apk : new String[]{oldApk, newApk}) {
            if (!Files.isRegularFile(Paths.get(apk))) {
                err.println(usageText());
                err.println("apkdiff: error: APK 不存在: " + apk);
                return 2;
            }
        }

        String oldMappingPath = options.oldMapping != null
                ? options.oldMapping : autodetectMapping(oldApk);
        String newMappingPath = options.newMapping != null
                ? options.newMapping : autodetectMapping(newApk);

        boolean console = formats.contains("console");
        if (console) {
            out.println("[1/4] 读取旧 APK: " + oldApk);
        }
        Mapping oldMapping = Mapping.load(oldMappingPath);
        ApkAnalysis old = ApkAnalyzer.analyze(oldApk, oldMapping);
        if (console) {
            out.println("      类 " + old.getClasses().size() + " 个，条目 "
                    + old.getEntries().size() + " 个"
                    + (oldMappingPath != null ? "，mapping: " + oldMappingPath : "（无 mapping）"));
            out.println("[2/4] 读取新 APK: " + newApk);
        }
        Mapping newMapping = Mapping.load(newMappingPath);
        ApkAnalysis latest = ApkAnalyzer.analyze(newApk, newMapping);
        if (console) {
            out.println("      类 " + latest.getClasses().size() + " 个，条目 "
                    + latest.getEntries().size() + " 个"
                    + (newMappingPath != null ? "，mapping: " + newMappingPath : "（无 mapping）"));
        }

        if (old.getClasses().isEmpty() && latest.getClasses().isEmpty()) {
            err.println("错误: 两个 APK 中都没有解析出任何 DEX 类。");
            return 2;
        }

        if (console) {
            out.println("[3/4] 计算差异 …");
        }
        DiffResult result = Differ.diff(
                old, latest, options.includeMeta, options.detectRenames);

        if (console) {
            out.println("[4/4] 输出报告 …");
            out.println();
            Reporter.printConsole(result, options.metric, options.top, options.full, out);
        }

        Path outDir = Paths.get(options.output);
        for (String format : formats) {
            Path target;
            switch (format) {
                case "json":
                    target = outDir.resolve("apkdiff.json");
                    Reporter.writeJson(result, target.toString(), options.metric);
                    break;
                case "html":
                    target = outDir.resolve("apkdiff.html");
                    Reporter.writeHtml(result, target.toString(), options.metric);
                    break;
                case "markdown":
                    target = outDir.resolve("apkdiff.md");
                    Reporter.writeMarkdown(result, target.toString(), options.metric);
                    break;
                default:
                    continue;
            }
            if (console) {
                out.println("  → " + target);
            }
        }

        if (!console) {
            out.println("报告已生成于 " + outDir.toAbsolutePath());
        }

        // Size gate: exit 1 when the new APK grew, so a CI step fails.
        if (options.failOnRegression && result.summaryLong("apk_size_delta") > 0) {
            return 1;
        }
        return 0;
    }

    public static void main(String[] args) {
        // JVM console output defaults to the platform encoding (GBK on Chinese Windows), which
        // garbles the Chinese report. Reports and terminal output are UTF-8, matching the
        // Python implementation. On legacy Windows consoles use `chcp 65001`.
        PrintStream utf8Out = new PrintStream(System.out, true, StandardCharsets.UTF_8);
        PrintStream utf8Err = new PrintStream(System.err, true, StandardCharsets.UTF_8);
        System.exit(runCli(args, utf8Out, utf8Err));
    }
}
