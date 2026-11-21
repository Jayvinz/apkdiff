#!/usr/bin/env node
import { existsSync, statSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import {
  ApkAnalysis,
  DiffResult,
  Mapping,
  analyzeApk,
  diffApks,
  loadMapping,
  printConsole,
  writeHtml,
  writeJson,
  writeMarkdown,
} from '@jayvinz/apkdiff-core';

/**
 * Command line entry point.
 *
 * Flow: parse arguments, analyse the old APK, analyse the new APK, diff, render reports.
 * `--fail-on-regression` makes the process exit 1 when the new APK is larger, which is how
 * a CI size gate works.
 */

const VALID_FORMATS = ['console', 'json', 'html', 'markdown'];

type LineWriter = (line: string) => void;

class CliError extends Error {
}

class HelpRequested extends Error {
}

interface Options {
  oldApk?: string;
  newApk?: string;
  oldMapping?: string;
  newMapping?: string;
  format: string;
  output: string;
  metric: string;
  top: number;
  full: boolean;
  includeMeta: boolean;
  detectRenames: boolean;
  failOnRegression: boolean;
}

function usageText(): string {
  return [
    'usage: apkdiff [-h] [--old-mapping OLD_MAPPING] [--new-mapping NEW_MAPPING]',
    '               [--format FORMAT] [-o OUTPUT] [--metric {compressed,uncompressed}]',
    '               [--top TOP] [--full] [--include-meta] [--detect-renames]',
    '               [--fail-on-regression]',
    '               old_apk new_apk',
    '',
    '对比两个 APK，按类 / 资源粒度输出体积变更报告。',
    '',
    'positional arguments:',
    '  old_apk               旧版本 APK 路径',
    '  new_apk               新版本 APK 路径',
    '',
    'options:',
    '  -h, --help            显示帮助并退出',
    '  --old-mapping OLD_MAPPING',
    '                        旧版本 ProGuard/R8 mapping.txt（默认自动探测）',
    '  --new-mapping NEW_MAPPING',
    '                        新版本 ProGuard/R8 mapping.txt（默认自动探测）',
    '  --format FORMAT       输出格式，逗号分隔：console,json,html,markdown（默认 console,json,html）',
    '  -o, --output OUTPUT   报告输出目录（默认 apkdiff-report）',
    '  --metric {compressed,uncompressed}',
    '                        排序与 Δ 显示所用的指标（默认 compressed）',
    '  --top TOP             控制台每种类型显示条数（默认 30）',
    '  --full                控制台显示全部条目',
    '  --include-meta        把 META-INF 纳入资源对比',
    '  --detect-renames      检测内容相同的资源重命名',
    '  --fail-on-regression  若新 APK 体积增大则以退出码 1 结束（便于 CI 使用）',
  ].join('\n');
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    format: 'console,json,html',
    output: 'apkdiff-report',
    metric: 'compressed',
    top: 30,
    full: false,
    includeMeta: false,
    detectRenames: false,
    failOnRegression: false,
  };
  const positional: string[] = [];
  let i = 0;

  const requiredValue = (flag: string): string => {
    if (i + 1 >= argv.length) {
      throw new CliError(`argument ${flag}: expected one argument`);
    }
    i += 1;
    return argv[i];
  };

  while (i < argv.length) {
    const arg = argv[i];
    const eq = arg.startsWith('--') ? arg.indexOf('=') : -1;
    const name = eq >= 0 ? arg.substring(0, eq) : arg;
    const inlineValue = eq >= 0 ? arg.substring(eq + 1) : null;

    switch (name) {
      case '-h':
      case '--help':
        throw new HelpRequested();
      case '--old-mapping':
        options.oldMapping = inlineValue ?? requiredValue(name);
        break;
      case '--new-mapping':
        options.newMapping = inlineValue ?? requiredValue(name);
        break;
      case '--format':
        options.format = inlineValue ?? requiredValue(name);
        break;
      case '-o':
      case '--output':
        options.output = inlineValue ?? requiredValue(name);
        break;
      case '--metric':
        options.metric = inlineValue ?? requiredValue(name);
        break;
      case '--top': {
        const raw = inlineValue ?? requiredValue(name);
        const value = Number(raw);
        if (!Number.isInteger(value)) {
          throw new CliError(`argument --top: invalid int value: '${raw}'`);
        }
        options.top = value;
        break;
      }
      case '--full':
        options.full = true;
        break;
      case '--include-meta':
        options.includeMeta = true;
        break;
      case '--detect-renames':
        options.detectRenames = true;
        break;
      case '--fail-on-regression':
        options.failOnRegression = true;
        break;
      default:
        if (name.startsWith('-')) {
          throw new CliError(`unrecognized arguments: ${arg}`);
        }
        positional.push(arg);
        break;
    }
    i += 1;
  }

  if (positional.length === 0) {
    throw new CliError('the following arguments are required: old_apk, new_apk');
  }
  if (positional.length === 1) {
    throw new CliError('the following arguments are required: new_apk');
  }
  if (positional.length > 2) {
    throw new CliError(`unrecognized arguments: ${positional.slice(2).join(' ')}`);
  }
  options.oldApk = positional[0];
  options.newApk = positional[1];
  return options;
}

/** Look for a mapping file next to the APK. */
function autodetectMapping(apkPath: string): string | null {
  const apk = resolve(apkPath);
  const fileName = basename(apk);
  const dot = fileName.lastIndexOf('.');
  const stem = dot > 0 ? fileName.substring(0, dot) : fileName;
  const candidates = [
    join(dirname(apk), `${stem}-mapping.txt`),
    join(dirname(apk), `${stem}.mapping.txt`),
    join(dirname(apk), 'mapping.txt'),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate) && isFile(candidate)) {
      return candidate;
    }
  }
  return null;
}

/** Run the CLI. Returns the process exit code. */
export function runCli(
  argv: string[],
  out: LineWriter,
  err: LineWriter,
): number {
  let options: Options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    if (error instanceof HelpRequested) {
      out(usageText());
      return 0;
    }
    if (error instanceof CliError) {
      err(usageText());
      err(`apkdiff: error: ${error.message}`);
      return 2;
    }
    throw error;
  }

  const formats = options.format.split(',')
    .map((format) => format.trim().toLowerCase())
    .filter((format) => format !== '');
  const invalid = formats.filter((format) => !VALID_FORMATS.includes(format));
  if (invalid.length > 0) {
    err(usageText());
    err(`apkdiff: error: 不支持的输出格式: ${invalid.join(', ')}；可选: ${VALID_FORMATS.join(', ')}`);
    return 2;
  }
  if (options.metric !== 'compressed' && options.metric !== 'uncompressed') {
    err(usageText());
    err(`apkdiff: error: argument --metric: invalid choice: '${options.metric}'`);
    return 2;
  }

  const oldApk = options.oldApk!;
  const newApk = options.newApk!;
  for (const apk of [oldApk, newApk]) {
    if (!existsSync(apk) || !isFile(apk)) {
      err(usageText());
      err(`apkdiff: error: APK 不存在: ${apk}`);
      return 2;
    }
  }

  const oldMappingPath = options.oldMapping ?? autodetectMapping(oldApk);
  const newMappingPath = options.newMapping ?? autodetectMapping(newApk);

  const consoleOut = formats.includes('console');
  if (consoleOut) {
    out(`[1/4] 读取旧 APK: ${oldApk}`);
  }
  const oldMapping: Mapping = loadMapping(oldMappingPath);
  const oldApkAnalysis: ApkAnalysis = analyzeApk(oldApk, oldMapping);
  if (consoleOut) {
    out(`      类 ${oldApkAnalysis.classes.size} 个，条目 ${oldApkAnalysis.entries.size} 个`
      + (oldMappingPath !== null ? `，mapping: ${oldMappingPath}` : '（无 mapping）'));
    out(`[2/4] 读取新 APK: ${newApk}`);
  }
  const newMapping: Mapping = loadMapping(newMappingPath);
  const newApkAnalysis: ApkAnalysis = analyzeApk(newApk, newMapping);
  if (consoleOut) {
    out(`      类 ${newApkAnalysis.classes.size} 个，条目 ${newApkAnalysis.entries.size} 个`
      + (newMappingPath !== null ? `，mapping: ${newMappingPath}` : '（无 mapping）'));
  }

  if (oldApkAnalysis.classes.size === 0 && newApkAnalysis.classes.size === 0) {
    err('错误: 两个 APK 中都没有解析出任何 DEX 类。');
    return 2;
  }

  if (consoleOut) {
    out('[3/4] 计算差异 …');
  }
  const result: DiffResult = diffApks(
    oldApkAnalysis, newApkAnalysis, options.includeMeta, options.detectRenames);

  if (consoleOut) {
    out('[4/4] 输出报告 …');
    out('');
    printConsole(result, options.metric, options.top, options.full, out);
  }

  const outDir = options.output;
  for (const format of formats) {
    let target: string;
    switch (format) {
      case 'json':
        target = join(outDir, 'apkdiff.json');
        writeJson(result, target, options.metric);
        break;
      case 'html':
        target = join(outDir, 'apkdiff.html');
        writeHtml(result, target, options.metric);
        break;
      case 'markdown':
        target = join(outDir, 'apkdiff.md');
        writeMarkdown(result, target, options.metric);
        break;
      default:
        continue;
    }
    if (consoleOut) {
      out(`  → ${target}`);
    }
  }

  if (!consoleOut) {
    out(`报告已生成于 ${resolve(outDir)}`);
  }

  // Size gate: exit 1 when the new APK grew, so a CI step fails.
  if (options.failOnRegression && result.summaryLong('apk_size_delta') > 0) {
    return 1;
  }
  return 0;
}

function main(): void {
  const out: LineWriter = (line) => process.stdout.write(`${line}\n`);
  const err: LineWriter = (line) => process.stderr.write(`${line}\n`);
  process.exitCode = runCli(process.argv.slice(2), out, err);
}

if (require.main === module) {
  main();
}

export { usageText };
