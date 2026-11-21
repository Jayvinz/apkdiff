export * from './util';
export * from './dex';
export * from './mapping';
export * from './apk';
export * from './diff';
export * from './report';

import { analyzeApk } from './apk';
import { diffApks } from './diff';
import { loadMapping } from './mapping';
import {
  buildJson,
  printConsole,
  writeHtml,
  writeJson,
  writeMarkdown,
} from './report';
import { humanDelta, humanSize } from './util';

/**
 * Namespace-style facade, mirroring the JVM `ApkDiff` class.
 *
 * ```ts
 * const old = ApkDiff.analyze('old.apk', ApkDiff.mapping('old/mapping.txt'));
 * const result = ApkDiff.diff(old, ApkDiff.analyze('new.apk'), false, true);
 * ApkDiff.writeJsonReport(result, 'report/apkdiff.json', 'compressed');
 * ```
 */
export const ApkDiff = {
  mapping: loadMapping,
  analyze: analyzeApk,
  diff: diffApks,
  printReport: printConsole,
  json: buildJson,
  writeJsonReport: writeJson,
  writeHtmlReport: writeHtml,
  writeMarkdownReport: writeMarkdown,
  size: humanSize,
  sizeDelta: humanDelta,
};
