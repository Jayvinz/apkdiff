import { statSync } from 'node:fs';
import { DexAnalysis, DexFile, descriptorToClassName } from './dex';
import { Mapping } from './mapping';
import { SizeBreakdown, joinNonEmpty, messageOf, sha256Hex } from './util';
import { ZipArchive, ZipEntry } from './zip';

const RESOURCE_CATEGORIES = new Set([
  'res', 'assets', 'resources', 'manifest', 'lib', 'meta', 'other',
]);

/** One file inside the APK zip. */
export class ApkEntry {
  constructor(
    public readonly name: string,
    public readonly category: string,
    public readonly compressSize: number,
    public readonly fileSize: number,
    public readonly crc: number,
    public readonly sha256: string,
  ) {
  }

  /**
   * META-INF is opt-in via `--include-meta`; the filtering happens in the differ,
   * so it must be included in the raw inventory here.
   */
  isResource(): boolean {
    return RESOURCE_CATEGORIES.has(this.category);
  }
}

/** A class in the APK, with its deobfuscated display name and attributed bytes. */
export class ApkClass {
  constructor(
    public readonly name: string,
    public readonly rawName: string,
    public readonly dex: string,
    public size: number,
    public compressedSize: number,
    public breakdown: SizeBreakdown,
    public contentHash: string,
    public readonly methods: number,
    public readonly fields: number,
    public partial: boolean,
    public warning: string,
  ) {
  }

  asMap(): Record<string, unknown> {
    return {
      name: this.name,
      raw_name: this.rawName,
      dex: this.dex,
      size: this.size,
      compressed_size: this.compressedSize,
      methods: this.methods,
      fields: this.fields,
      breakdown: this.breakdown.asMap(),
      content_hash: this.contentHash,
    };
  }
}

/** Inventory and dex analysis for one APK. */
export class ApkAnalysis {
  readonly entries = new Map<string, ApkEntry>();
  readonly classes = new Map<string, ApkClass>();
  readonly dexFiles: DexAnalysis[] = [];
  readonly warnings: string[] = [];

  constructor(
    public readonly path: string,
    public fileSize: number,
  ) {
  }

  /**
   * Resource entries participating in the comparison. META-INF is opt-in, so the
   * default includes everything; callers pass `false` to skip signature files.
   */
  resourceEntries(includeMeta = true): Map<string, ApkEntry> {
    const out = new Map<string, ApkEntry>();
    for (const [name, entry] of this.entries) {
      if (entry.isResource() && (includeMeta || entry.category !== 'meta')) {
        out.set(name, entry);
      }
    }
    return out;
  }

  totalClassBytes(): number {
    let total = 0;
    for (const cls of this.classes.values()) {
      total += cls.size;
    }
    return total;
  }

  totalClassCompressedBytes(): number {
    let total = 0;
    for (const cls of this.classes.values()) {
      total += cls.compressedSize;
    }
    return total;
  }

  unattributedDexBytes(): number {
    let total = 0;
    for (const dex of this.dexFiles) {
      total += dex.unattributed;
    }
    return total;
  }
}

/** POSIX-style path normalisation (the subset needed by zip entry names). */
export function posixNormpath(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  if (normalized === '') {
    return '.';
  }
  const absolute = normalized.startsWith('/');
  const trailingSlash = normalized.endsWith('/');
  const out: string[] = [];
  for (const part of normalized.split('/')) {
    if (part === '' || part === '.') {
      continue;
    }
    if (part === '..') {
      if (out.length > 0 && out[out.length - 1] !== '..') {
        out.pop();
      } else if (!absolute) {
        out.push('..');
      }
    } else {
      out.push(part);
    }
  }
  const joined = out.join('/');
  if (absolute) {
    const result = `/${joined}`;
    return trailingSlash && !result.endsWith('/') ? `${result}/` : result;
  }
  if (joined === '') {
    return '.';
  }
  return trailingSlash ? `${joined}/` : joined;
}

export function categorize(name: string): string {
  const normalized = posixNormpath(name).replace(/\\/g, '/');
  const base = normalized.substring(normalized.lastIndexOf('/') + 1);
  if (/^classes\d*\.dex$/i.test(base) && !normalized.includes('/')) {
    return 'dex';
  }
  if (normalized.startsWith('res/')) {
    return 'res';
  }
  if (normalized.startsWith('assets/')) {
    return 'assets';
  }
  if (normalized.startsWith('lib/')) {
    return 'lib';
  }
  if (normalized.startsWith('META-INF/')) {
    return 'meta';
  }
  if (normalized === 'AndroidManifest.xml') {
    return 'manifest';
  }
  if (normalized === 'resources.arsc') {
    return 'resources';
  }
  return 'other';
}

function dexOrder(name: string): number {
  const base = name.substring(name.lastIndexOf('/') + 1);
  if (base.toLowerCase() === 'classes.dex') {
    return 0;
  }
  const match = /^classes(\d+)\.dex$/i.exec(base);
  if (match !== null) {
    const value = Number.parseInt(match[1], 10);
    return Number.isNaN(value) ? 9999 : value;
  }
  return 9999;
}

/**
 * Read an APK and build the class / resource inventory.
 *
 * Compressed class size is an estimate: a dex is compressed as one blob, so the dex-wide
 * compression ratio is applied to each class's uncompressed size instead.
 */
export function analyzeApk(
  path: string,
  mapping: Mapping | null = null,
  hashContent = true,
): ApkAnalysis {
  const result = new ApkAnalysis(path, 0);
  try {
    result.fileSize = statSync(path).size;
  } catch {
    // Keep file size 0 when stat fails; the open error below will be reported.
  }

  let archive: ZipArchive;
  try {
    archive = new ZipArchive(path);
  } catch (error) {
    result.warnings.push(`cannot open APK: ${messageOf(error)}`);
    return result;
  }

  const dexContents = new Map<string, Buffer>();
  for (const entry of archive.entries()) {
    if (entry.name.endsWith('/')) {
      continue;
    }
    const name = entry.name.replace(/\\/g, '/');
    const category = categorize(name);
    let digest = '';
    if (hashContent) {
      try {
        // Read the entry once: hashing and, for dex files, later analysis need it.
        const content = archive.read(entry);
        digest = sha256Hex(content);
        if (category === 'dex') {
          dexContents.set(name, content);
        }
      } catch (error) {
        result.warnings.push(
          `cannot hash ${name}: ${messageOf(error)}`);
      }
    }
    result.entries.set(name, new ApkEntry(
      name,
      category,
      entry.compressedSize,
      entry.fileSize,
      entry.crc,
      digest,
    ));
  }

  // Analyse every classes*.dex
  const dexNames: string[] = [];
  for (const entry of result.entries.values()) {
    if (entry.category === 'dex') {
      dexNames.push(entry.name);
    }
  }
  dexNames.sort((a, b) => {
    const byOrder = dexOrder(a) - dexOrder(b);
    return byOrder !== 0 ? byOrder : (a < b ? -1 : a > b ? 1 : 0);
  });

  for (const dexName of dexNames) {
    let analysis: DexAnalysis;
    try {
      const zipEntry: ZipEntry | undefined = archive.getEntry(dexName);
      if (zipEntry === undefined) {
        throw new Error(`missing dex entry ${dexName}`);
      }
      const cached = dexContents.get(dexName);
      analysis = new DexFile(cached ?? archive.read(zipEntry), dexName).analyze();
    } catch (error) {
      result.warnings.push(
        `cannot analyze ${dexName}: ${messageOf(error)}`);
      continue;
    }
    result.dexFiles.push(analysis);
    for (const warning of analysis.warnings) {
      result.warnings.push(`${dexName}: ${warning}`);
    }

    const entry = result.entries.get(dexName);
    if (entry === undefined) {
      continue;
    }
    // Compressed size is an estimate: apply the dex-wide compression ratio to each
    // class's uncompressed size.
    const ratio = entry.fileSize !== 0
      ? entry.compressSize / entry.fileSize
      : 0;
    for (const cls of analysis.classes) {
      const displayName = mapping !== null
        ? mapping.deobfuscateDescriptor(cls.name)
        : descriptorToClassName(cls.name);
      const estimatedCompressed = Math.round(cls.size * ratio);
      const existing = result.classes.get(displayName);
      if (existing !== undefined) {
        // The same class appearing in multiple dex files is rare but possible: conservatively
        // sum the sizes and combine hashes so it cannot silently disappear.
        existing.size += cls.size;
        existing.compressedSize += estimatedCompressed;
        existing.breakdown = existing.breakdown.plus(cls.breakdown);
        existing.contentHash = sha256Hex(
          Buffer.from(existing.contentHash + cls.contentHash, 'ascii'));
        existing.partial = existing.partial || cls.partial;
        existing.warning = joinNonEmpty(existing.warning, cls.warning);
      } else {
        result.classes.set(displayName, new ApkClass(
          displayName,
          descriptorToClassName(cls.name),
          dexName,
          cls.size,
          estimatedCompressed,
          cls.breakdown,
          cls.contentHash,
          cls.methods,
          cls.fields,
          cls.partial,
          cls.warning,
        ));
      }
    }
  }
  return result;
}
