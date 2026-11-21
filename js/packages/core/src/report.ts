import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import {
  ADDED, Change, DELETED, DiffResult, MODIFIED, RENAMED, STATUS_LABEL, statusLabel,
} from './diff';
import { writeJsonValue } from './json-writer';
import { HTML_TEMPLATE } from './template';
import { humanDelta, humanSize } from './util';

/**
 * Renders the diff as console output, JSON, HTML, or Markdown.
 *
 * All four formats share one data source and one size-formatting helper, so the same number
 * reads identically everywhere. JSON stores exact integer byte counts; only human-facing
 * output converts to KB with 2 decimals.
 */

export type LineWriter = (line: string) => void;

function statusMark(status: string): string {
  switch (status) {
    case ADDED:
      return '+';
    case DELETED:
      return '-';
    case MODIFIED:
      return '~';
    case RENAMED:
      return '>';
    default:
      return '?';
  }
}

function metricUnit(metric: string): string {
  return metric === 'compressed' ? 'APK 压缩字节' : '未压缩字节';
}

// ---------------------------------------------------------------------------
// width helpers (terminal tables may contain Chinese labels)
// ---------------------------------------------------------------------------

function isWideCodePoint(cp: number): boolean {
  return (cp >= 0x1100 && cp <= 0x115f)
    || (cp >= 0x2329 && cp <= 0x232a)
    || (cp >= 0x2e80 && cp <= 0xa4cf && cp !== 0x303f)
    || (cp >= 0xac00 && cp <= 0xd7a3)
    || (cp >= 0xf900 && cp <= 0xfaff)
    || (cp >= 0xfe10 && cp <= 0xfe19)
    || (cp >= 0xfe30 && cp <= 0xfe6f)
    || (cp >= 0xff00 && cp <= 0xff60)
    || (cp >= 0xffe0 && cp <= 0xffe6)
    || (cp >= 0x1f300 && cp <= 0x1f64f)
    || (cp >= 0x1f900 && cp <= 0x1f9ff)
    || (cp >= 0x20000 && cp <= 0x3fffd);
}

function displayWidth(text: string): number {
  let width = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0)!;
    width += isWideCodePoint(cp) ? 2 : 1;
  }
  return width;
}

function pad(text: string, width: number): string {
  return text + ' '.repeat(Math.max(0, width - displayWidth(text)));
}

function padChars(text: string, width: number): string {
  return text + ' '.repeat(Math.max(0, width - text.length));
}

function padStart(value: number, width: number): string {
  return String(value).padStart(width);
}

function byImpact(changes: Change[], metric: string): Change[] {
  return [...changes].sort(
    (a, b) => Math.abs(b.sizeFor(metric)) - Math.abs(a.sizeFor(metric)));
}

// ---------------------------------------------------------------------------
// console
// ---------------------------------------------------------------------------

function printTable(
  title: string,
  changes: Change[],
  metric: string,
  limit: number,
  out: LineWriter,
): void {
  out('');
  out(`${title}  (共 ${changes.length} 项，显示前 ${Math.min(limit, changes.length)} 项)`);
  if (changes.length === 0) {
    out('  （无）');
    return;
  }
  let shown = byImpact(changes, metric);
  if (limit < shown.length) {
    shown = shown.slice(0, Math.max(0, limit));
  }
  let nameW = 0;
  for (const change of shown) {
    nameW = Math.max(nameW, displayWidth(change.key));
  }
  nameW = Math.min(72, nameW);
  nameW = Math.max(nameW, 12);
  const oldW = 11;
  const newW = 11;
  const deltaW = 13;
  const header = `  ${padChars('', 2)} ${padChars('状态', 6)} `
    + `${pad('名称', nameW)} ${pad('旧', oldW)} ${pad('新', newW)} ${pad('Δ', deltaW)}`;
  out(header);
  out(`  ${'-'.repeat(header.length - 2)}`);
  for (const c of shown) {
    let name = c.key;
    if (displayWidth(name) > nameW) {
      name = `${name.substring(0, Math.max(0, nameW - 3))}...`;
    }
    const old = c.oldFor(metric);
    const newValue = c.newFor(metric);
    const delta = c.sizeFor(metric);
    out(`  ${statusMark(c.status)}  ${pad(statusLabel(c.status), 6)} `
      + `${pad(name, nameW)} ${pad(humanSize(old), oldW)} `
      + `${pad(humanSize(newValue), newW)} ${pad(humanDelta(delta), deltaW)}`);
    if (c.status === RENAMED && c.detail.renamed_from !== undefined) {
      out(`       └─ 原路径: ${c.detail.renamed_from}`);
    }
    const deltaObject = c.detail.breakdown_delta;
    if (typeof deltaObject === 'object' && deltaObject !== null) {
      const parts: string[] = [];
      for (const [key, value] of Object.entries(deltaObject)) {
        if (typeof value === 'number' && value !== 0) {
          parts.push(`${key} ${humanDelta(value)}`);
        }
      }
      if (parts.length > 0) {
        out(`       └─ 明细: ${parts.join(' ')}`);
      }
    }
  }
}

/** Print the console report. */
export function printConsole(
  result: DiffResult,
  metric = 'compressed',
  top = 30,
  full = false,
  out: LineWriter = console.log,
): void {
  const limit = full ? Number.POSITIVE_INFINITY : Math.max(0, top);
  const unit = metricUnit(metric);

  out('='.repeat(78));
  out('APK DIFF REPORT');
  out('='.repeat(78));
  out(`  旧版本: ${result.oldAnalysis.path}`);
  out(`  新版本: ${result.newAnalysis.path}`);
  out(`  排序/主指标: ${unit}`);
  out('');
  out('  ── 包体总览 ──');
  out(`  APK 文件          ${humanSize(result.summaryLong('old_apk_size'))} → `
    + `${humanSize(result.summaryLong('new_apk_size'))}   `
    + `Δ ${humanDelta(result.summaryLong('apk_size_delta'))}`);
  out(`  代码(DEX,估算压缩) ${humanSize(result.summaryLong('old_class_compressed'))} → `
    + `${humanSize(result.summaryLong('new_class_compressed'))}   `
    + `Δ ${humanDelta(result.summaryLong('class_compressed_delta'))}`);
  out(`  代码(DEX,归属原始) ${humanSize(result.summaryLong('old_class_bytes'))} → `
    + `${humanSize(result.summaryLong('new_class_bytes'))}   `
    + `Δ ${humanDelta(result.summaryLong('class_bytes_delta'))}`);
  out(`  资源(压缩)        ${humanSize(result.summaryLong('old_resource_compressed'))} → `
    + `${humanSize(result.summaryLong('new_resource_compressed'))}   `
    + `Δ ${humanDelta(result.summaryLong('resource_compressed_delta'))}`);
  out(`  资源(原始)        ${humanSize(result.summaryLong('old_resource_bytes'))} → `
    + `${humanSize(result.summaryLong('new_resource_bytes'))}   `
    + `Δ ${humanDelta(result.summaryLong('resource_bytes_delta'))}`);
  out('');
  out('  ── 变更统计 ──');
  out(`  类:   新增 ${padStart(result.summaryLong('class_added'), 4)}  `
    + `删除 ${padStart(result.summaryLong('class_deleted'), 4)}  `
    + `修改 ${padStart(result.summaryLong('class_modified'), 4)}   `
    + `(旧 ${result.summaryLong('class_count_old')} → 新 ${result.summaryLong('class_count_new')})`);
  out(`  资源: 新增 ${padStart(result.summaryLong('resource_added'), 4)}  `
    + `删除 ${padStart(result.summaryLong('resource_deleted'), 4)}  `
    + `修改 ${padStart(result.summaryLong('resource_modified'), 4)}  `
    + `重命名 ${padStart(result.summaryLong('resource_renamed'), 4)}`);

  printTable('代码类变更', result.classes, metric, limit, out);
  printTable('资源文件变更', result.resources, metric, limit, out);

  const warnings = [...result.oldAnalysis.warnings, ...result.newAnalysis.warnings];
  if (warnings.length > 0) {
    out('');
    out(`  ⚠ 解析警告 ${warnings.length} 条:`);
    for (const warning of warnings.slice(0, 20)) {
      out(`    - ${warning}`);
    }
    if (warnings.length > 20) {
      out(`    ... 另有 ${warnings.length - 20} 条`);
    }
  }
}

// ---------------------------------------------------------------------------
// JSON
// ---------------------------------------------------------------------------

/** Build the object written to `apkdiff.json`. */
export function buildJson(result: DiffResult, metric: string): Record<string, unknown> {
  return {
    schema_version: 1,
    metric,
    old: {
      path: result.oldAnalysis.path,
      file_size: result.oldAnalysis.fileSize,
      warnings: result.oldAnalysis.warnings,
    },
    new: {
      path: result.newAnalysis.path,
      file_size: result.newAnalysis.fileSize,
      warnings: result.newAnalysis.warnings,
    },
    summary: result.summary,
    classes: byImpact(result.classes, metric).map((change) => change.asMap()),
    resources: byImpact(result.resources, metric).map((change) => change.asMap()),
  };
}

export function writeJson(result: DiffResult, path: string, metric: string): void {
  writeFile(path, writeJsonValue(buildJson(result, metric)));
}

// ---------------------------------------------------------------------------
// Markdown
// ---------------------------------------------------------------------------

function appendMarkdownTable(
  lines: string[],
  title: string,
  changes: Change[],
  metric: string,
): void {
  lines.push(`## ${title}`);
  lines.push('');
  if (changes.length === 0) {
    lines.push('（无）');
    return;
  }
  lines.push('| 状态 | 名称 | 旧 | 新 | Δ |');
  lines.push('| --- | --- | ---: | ---: | ---: |');
  for (const c of byImpact(changes, metric)) {
    const old = c.oldFor(metric);
    const newValue = c.newFor(metric);
    const name = c.key.replace(/\|/g, '\\|');
    const extra = typeof c.detail.renamed_from === 'string'
      ? ` ← \`${c.detail.renamed_from}\`` : '';
    lines.push(`| ${statusLabel(c.status)} | \`${name}\`${extra} | `
      + `${humanSize(old)} | ${humanSize(newValue)} | ${humanDelta(c.sizeFor(metric))} |`);
  }
  lines.push('');
}

export function writeMarkdown(result: DiffResult, path: string, metric: string): void {
  const summary = result.summary;
  const lines: string[] = [];
  lines.push('# APK Diff Report');
  lines.push('');
  lines.push(`- 旧版本: \`${result.oldAnalysis.path}\``);
  lines.push(`- 新版本: \`${result.newAnalysis.path}\``);
  lines.push(`- 主指标: ${metricUnit(metric)}`);
  lines.push('');
  lines.push('## 总览');
  lines.push('');
  lines.push('| 指标 | 旧 | 新 | Δ |');
  lines.push('| --- | ---: | ---: | ---: |');
  const rows: Array<[string, string, string, string]> = [
    ['APK 文件', 'old_apk_size', 'new_apk_size', 'apk_size_delta'],
    ['代码 (DEX 归属, 原始)', 'old_class_bytes', 'new_class_bytes', 'class_bytes_delta'],
    ['代码 (DEX 归属, 压缩估算)', 'old_class_compressed', 'new_class_compressed',
      'class_compressed_delta'],
    ['资源 (原始)', 'old_resource_bytes', 'new_resource_bytes', 'resource_bytes_delta'],
    ['资源 (压缩)', 'old_resource_compressed', 'new_resource_compressed',
      'resource_compressed_delta'],
  ];
  for (const [label, oldKey, newKey, deltaKey] of rows) {
    lines.push(`| ${label} | ${humanSize(result.summaryLong(oldKey))} | `
      + `${humanSize(result.summaryLong(newKey))} | `
      + `${humanDelta(result.summaryLong(deltaKey))} |`);
  }
  lines.push('');
  lines.push('## 统计');
  lines.push('');
  lines.push(`- 类: 新增 ${summary.class_added} / 删除 ${summary.class_deleted} / `
    + `修改 ${summary.class_modified}`);
  lines.push(`- 资源: 新增 ${summary.resource_added} / 删除 ${summary.resource_deleted} / `
    + `修改 ${summary.resource_modified} / 重命名 ${summary.resource_renamed}`);
  lines.push('');
  appendMarkdownTable(lines, '代码类变更', result.classes, metric);
  appendMarkdownTable(lines, '资源文件变更', result.resources, metric);
  writeFile(path, lines.join('\n'));
}

// ---------------------------------------------------------------------------
// HTML
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  let out = '';
  for (const ch of text) {
    switch (ch) {
      case '&':
        out += '&amp;';
        break;
      case '<':
        out += '&lt;';
        break;
      case '>':
        out += '&gt;';
        break;
      case '"':
        out += '&quot;';
        break;
      case "'":
        out += '&#x27;';
        break;
      default:
        out += ch;
        break;
    }
  }
  return out;
}

function htmlRows(changes: Change[], metric: string): string {
  if (changes.length === 0) {
    return '<tr><td colspan="6" class="detail">（无变更）</td></tr>';
  }
  let maxImpact = 1;
  for (const change of changes) {
    maxImpact = Math.max(maxImpact, Math.abs(change.sizeFor(metric)));
  }
  let parts = '';
  for (const c of byImpact(changes, metric)) {
    const old = c.oldFor(metric);
    const newValue = c.newFor(metric);
    const delta = c.sizeFor(metric);
    const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
    const barColor = delta > 0 ? 'var(--red)' : 'var(--green)';
    const width = Math.max(2, Math.round(Math.abs(delta) / maxImpact * 100));
    const detailParts: string[] = [];
    if (typeof c.detail.renamed_from === 'string') {
      detailParts.push(`原路径 ${escapeHtml(c.detail.renamed_from)}`);
    }
    const deltaObject = c.detail.breakdown_delta;
    if (typeof deltaObject === 'object' && deltaObject !== null) {
      const inner: string[] = [];
      for (const [key, value] of Object.entries(deltaObject)) {
        if (typeof value === 'number' && value !== 0) {
          inner.push(`${key} ${humanDelta(value)}`);
        }
      }
      detailParts.push(inner.join(' '));
    }
    if (typeof c.detail.dex === 'string') {
      detailParts.push(`dex: ${escapeHtml(c.detail.dex)}`);
    }
    const detail = detailParts.join(' · ');
    const detailHtml = detail === '' ? '' : `<div class="detail">${detail}</div>`;
    parts += `<tr data-status="${c.status}" data-search="${escapeHtml(c.key.toLowerCase())}">`
      + `<td><span class="tag ${c.status}">${statusLabel(c.status)}</span></td>`
      + `<td><div class="name">${escapeHtml(c.key)}</div>${detailHtml}`
      + `<div class="bar"><i style="width:${width}%;background:${barColor}"></i></div></td>`
      + `<td class="num" data-v="${old}">${humanSize(old)}</td>`
      + `<td class="num" data-v="${newValue}">${humanSize(newValue)}</td>`
      + `<td class="num ${cls}" data-v="${delta}">${humanDelta(delta)}</td>`
      + `<td class="num" data-v="${Math.abs(delta)}">${humanSize(Math.abs(delta))}</td>`
      + '</tr>';
  }
  return parts;
}

function htmlTable(
  tableId: string,
  title: string,
  changes: Change[],
  metric: string,
): string {
  const statuses: Array<[string, string]> = [
    [ADDED, STATUS_LABEL[ADDED]], [DELETED, STATUS_LABEL[DELETED]],
    [MODIFIED, STATUS_LABEL[MODIFIED]], [RENAMED, STATUS_LABEL[RENAMED]],
  ];
  let pills = `<span class="pill active" data-pill-group="${tableId}" `
    + `data-status="all">全部 ${changes.length}</span>`;
  for (const [status, label] of statuses) {
    const count = changes.filter((change) => change.status === status).length;
    pills += `<span class="pill " data-pill-group="${tableId}" `
      + `data-status="${status}">${label} ${count}</span>`;
  }
  return `\n  <h2>${title} <span class="sub" style="display:inline">(${changes.length} 项)</span></h2>\n`
    + '  <div class="panel">\n'
    + '    <div class="toolbar">\n'
    + `      <input id="q_${tableId}" type="text" placeholder="搜索类名 / 文件名…">\n`
    + `      ${pills}\n`
    + '    </div>\n'
    + `    <table id="${tableId}">\n`
    + '      <thead><tr>\n'
    + '        <th data-sort>状态</th><th data-sort>名称</th>\n'
    + '        <th class="num" data-sort>旧</th><th class="num" data-sort>新</th>\n'
    + '        <th class="num" data-sort>Δ</th><th class="num" data-sort>Δ 大小</th>\n'
    + '      </tr></thead>\n'
    + `      <tbody>${htmlRows(changes, metric)}</tbody>\n`
    + '    </table>\n'
    + '  </div>';
}

export function writeHtml(result: DiffResult, path: string, metric: string): void {
  const cards: Array<[string, string, string, string]> = [
    ['APK 文件', 'old_apk_size', 'new_apk_size', 'apk_size_delta'],
    ['代码 (压缩估算)', 'old_class_compressed', 'new_class_compressed',
      'class_compressed_delta'],
    ['代码 (原始归属)', 'old_class_bytes', 'new_class_bytes', 'class_bytes_delta'],
    ['资源 (压缩)', 'old_resource_compressed', 'new_resource_compressed',
      'resource_compressed_delta'],
    ['资源 (原始)', 'old_resource_bytes', 'new_resource_bytes', 'resource_bytes_delta'],
  ];
  let cardHtml = '';
  for (const [label, oldKey, newKey, deltaKey] of cards) {
    const old = result.summaryLong(oldKey);
    const newValue = result.summaryLong(newKey);
    const delta = result.summaryLong(deltaKey);
    const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
    cardHtml += `<div class="card"><div class="label">${label}</div>`
      + `<div class="value">${humanSize(newValue)}</div>`
      + `<div class="delta ${cls}">${humanDelta(delta)} &nbsp;(旧 ${humanSize(old)})</div></div>`;
  }

  const warnings = [...result.oldAnalysis.warnings, ...result.newAnalysis.warnings];
  let warnHtml = '';
  if (warnings.length > 0) {
    const items = warnings.slice(0, 50)
      .map((warning) => `<li>${escapeHtml(warning)}</li>`).join('');
    warnHtml = `<div class="warn"><b>解析警告 (${warnings.length})</b><ul>${items}</ul></div>`;
  }

  const body = HTML_TEMPLATE
    .replace('__OLD__', () => escapeHtml(result.oldAnalysis.path))
    .replace('__NEW__', () => escapeHtml(result.newAnalysis.path))
    .replace('__METRIC__', () => metricUnit(metric))
    .replace('__CARDS__', () => cardHtml)
    .replace('__CLASS_TABLE__', () => htmlTable('classes', '代码类变更', result.classes, metric))
    .replace('__RES_TABLE__', () => htmlTable('resources', '资源文件变更', result.resources, metric))
    .replace('__WARNINGS__', () => warnHtml)
    .replace('__JS_BIND__', () => "bindTable('q_classes','classes',"
      + "document.querySelectorAll('[data-pill-group=classes]'));\n"
      + "bindTable('q_resources','resources',"
      + "document.querySelectorAll('[data-pill-group=resources]'));");

  writeFile(path, body);
}

// ---------------------------------------------------------------------------
// file helper
// ---------------------------------------------------------------------------

function writeFile(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, 'utf8');
}
