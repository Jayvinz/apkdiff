import { ApkAnalysis, ApkClass, ApkEntry } from './apk';
import { compareStrings, fixedDecimal, joinNonEmpty } from './util';

export const ADDED = 'added';
export const DELETED = 'deleted';
export const MODIFIED = 'modified';
export const RENAMED = 'renamed';
export const UNCHANGED = 'unchanged';

export const STATUS_LABEL: Record<string, string> = {
  [ADDED]: '新增',
  [DELETED]: '删除',
  [MODIFIED]: '修改',
  [RENAMED]: '重命名',
  [UNCHANGED]: '未变',
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

/** One changed class or resource. */
export class Change {
  constructor(
    public readonly key: string,
    public readonly kind: 'class' | 'resource',
    public readonly status: string,
    public readonly oldSize: number,
    public readonly newSize: number,
    public readonly oldCompressed: number,
    public readonly newCompressed: number,
    public readonly oldHash: string,
    public readonly newHash: string,
    public readonly detail: Record<string, unknown>,
  ) {
  }

  get delta(): number {
    return this.newSize - this.oldSize;
  }

  get compressedDelta(): number {
    return this.newCompressed - this.oldCompressed;
  }

  sizeFor(metric: string): number {
    return metric === 'compressed' ? this.compressedDelta : this.delta;
  }

  oldFor(metric: string): number {
    return metric === 'compressed' ? this.oldCompressed : this.oldSize;
  }

  newFor(metric: string): number {
    return metric === 'compressed' ? this.newCompressed : this.newSize;
  }

  asMap(): Record<string, unknown> {
    return {
      key: this.key,
      kind: this.kind,
      status: this.status,
      status_label: statusLabel(this.status),
      old_size: this.oldSize,
      new_size: this.newSize,
      delta: this.delta,
      old_compressed: this.oldCompressed,
      new_compressed: this.newCompressed,
      compressed_delta: this.compressedDelta,
      old_hash: this.oldHash,
      new_hash: this.newHash,
      detail: this.detail,
    };
  }
}

/** Full result of comparing two APKs. */
export class DiffResult {
  constructor(
    public readonly oldAnalysis: ApkAnalysis,
    public readonly newAnalysis: ApkAnalysis,
    public readonly classes: Change[],
    public readonly resources: Change[],
    public readonly summary: Record<string, number>,
  ) {
  }

  getChanges(): Change[] {
    return [...this.classes, ...this.resources];
  }

  /** Read a numeric summary value. */
  summaryLong(key: string): number {
    const value = this.summary[key];
    if (typeof value !== 'number') {
      throw new Error(`summary value is not numeric: ${key}`);
    }
    return value;
  }
}

function classChanges(oldAnalysis: ApkAnalysis, newAnalysis: ApkAnalysis): Change[] {
  const out: Change[] = [];
  const allKeys = Array.from(new Set([
    ...oldAnalysis.classes.keys(),
    ...newAnalysis.classes.keys(),
  ])).sort(compareStrings);
  for (const key of allKeys) {
    const o: ApkClass | undefined = oldAnalysis.classes.get(key);
    const n: ApkClass | undefined = newAnalysis.classes.get(key);
    if (o === undefined && n !== undefined) {
      out.push(new Change(
        key, 'class', ADDED,
        0, n.size, 0, n.compressedSize,
        '', n.contentHash,
        {
          raw_name: n.rawName,
          dex: n.dex,
          methods: n.methods,
          fields: n.fields,
          breakdown: n.breakdown.asMap(),
          partial: n.partial,
          warning: n.warning,
        },
      ));
    } else if (o !== undefined && n === undefined) {
      out.push(new Change(
        key, 'class', DELETED,
        o.size, 0, o.compressedSize, 0,
        o.contentHash, '',
        {
          raw_name: o.rawName,
          dex: o.dex,
          methods: o.methods,
          fields: o.fields,
          breakdown: o.breakdown.asMap(),
          partial: o.partial,
          warning: o.warning,
        },
      ));
    } else if (o !== undefined && n !== undefined) {
      if (o.contentHash === n.contentHash) {
        // Same semantic fingerprint means the source did not change, even if index-pool
        // reshuffling shifted the attributed byte counts a little.
        continue;
      }
      const oldBreakdown = o.breakdown.asMap();
      const newBreakdown = n.breakdown.asMap();
      const breakdownDelta: Record<string, number> = {};
      for (const k of Object.keys(oldBreakdown)) {
        breakdownDelta[k] = (newBreakdown[k] ?? 0) - oldBreakdown[k];
      }
      out.push(new Change(
        key, 'class', MODIFIED,
        o.size, n.size,
        o.compressedSize, n.compressedSize,
        o.contentHash, n.contentHash,
        {
          raw_name: n.rawName,
          dex: o.dex !== n.dex ? `${o.dex} -> ${n.dex}` : n.dex,
          methods_before: o.methods,
          methods_after: n.methods,
          fields_before: o.fields,
          fields_after: n.fields,
          breakdown_delta: breakdownDelta,
          partial: o.partial || n.partial,
          warning: joinNonEmpty(o.warning, n.warning),
        },
      ));
    }
  }
  return out;
}

function first16(value: string): string {
  return value.substring(0, Math.min(16, value.length));
}

function compressionPercent(compressSize: number, fileSize: number): number {
  if (fileSize === 0) {
    return 0.0;
  }
  return (1 - compressSize / fileSize) * 100;
}

function entryChange(
  key: string,
  o: ApkEntry | null,
  n: ApkEntry | null,
  status: string,
  renamedFrom: string | null = null,
): Change {
  const detail: Record<string, unknown> = { category: (n ?? o)!.category };
  if (o !== null && n !== null) {
    detail.crc_before = o.crc.toString(16).padStart(8, '0');
    detail.crc_after = n.crc.toString(16).padStart(8, '0');
    detail.hash_before = first16(o.sha256);
    detail.hash_after = first16(n.sha256);
    detail.compression_before = fixedDecimal(
      compressionPercent(o.compressSize, o.fileSize), 1);
    detail.compression_after = fixedDecimal(
      compressionPercent(n.compressSize, n.fileSize), 1);
  }
  if (renamedFrom !== null && renamedFrom !== '') {
    detail.renamed_from = renamedFrom;
  }
  return new Change(
    key,
    'resource',
    status,
    o !== null ? o.fileSize : 0,
    n !== null ? n.fileSize : 0,
    o !== null ? o.compressSize : 0,
    n !== null ? n.compressSize : 0,
    o !== null ? o.sha256 : '',
    n !== null ? n.sha256 : '',
    detail,
  );
}

function resourceChanges(
  oldEntries: Map<string, ApkEntry>,
  newEntries: Map<string, ApkEntry>,
  detectRenames: boolean,
): Change[] {
  const added = [...newEntries.keys()].filter((name) => !oldEntries.has(name)).sort(compareStrings);
  const deleted = [...oldEntries.keys()].filter((name) => !newEntries.has(name)).sort(compareStrings);

  const changes: Change[] = [];
  const pairedOld = new Set<string>();
  const pairedNew = new Set<string>();

  if (detectRenames) {
    // Group deleted files by hash, then look for added files with the same hash.
    const byHash = new Map<string, string[]>();
    for (const name of deleted) {
      const h = oldEntries.get(name)!.sha256;
      if (h !== '') {
        const list = byHash.get(h) ?? [];
        list.push(name);
        byHash.set(h, list);
      }
    }
    for (const name of added) {
      const h = newEntries.get(name)!.sha256;
      const candidates = h === '' ? undefined : byHash.get(h);
      if (candidates === undefined || candidates.length === 0) {
        continue;
      }
      const oldName = candidates.shift()!;
      if (candidates.length === 0) {
        byHash.delete(h);
      }
      pairedOld.add(oldName);
      pairedNew.add(name);
      changes.push(entryChange(
        name, oldEntries.get(oldName)!, newEntries.get(name)!, RENAMED, oldName));
    }
  }

  for (const name of Array.from(newEntries.keys()).sort(compareStrings)) {
    const o = oldEntries.get(name);
    const n = newEntries.get(name)!;
    if (o !== undefined) {
      if (o.sha256 !== n.sha256 || o.fileSize !== n.fileSize) {
        changes.push(entryChange(name, o, n, MODIFIED));
      }
    } else if (!pairedNew.has(name)) {
      changes.push(entryChange(name, null, n, ADDED));
    }
  }

  for (const name of deleted) {
    if (!pairedOld.has(name)) {
      changes.push(entryChange(name, oldEntries.get(name)!, null, DELETED));
    }
  }

  return changes;
}

function count(changes: Change[], status: string): number {
  return changes.filter((change) => change.status === status).length;
}

function resourceTotals(entries: Map<string, ApkEntry>): { bytes: number; compressed: number } {
  let bytes = 0;
  let compressed = 0;
  for (const entry of entries.values()) {
    bytes += entry.fileSize;
    compressed += entry.compressSize;
  }
  return { bytes, compressed };
}

/**
 * Compares two APK analyses and classifies every change.
 *
 * Classes compare by semantic fingerprint; resources by content SHA-256. Renames are
 * detected only when requested: a deleted entry and an added entry with the same content
 * hash are reported as one rename.
 */
export function diffApks(
  oldAnalysis: ApkAnalysis,
  newAnalysis: ApkAnalysis,
  includeMeta = false,
  detectRenames = false,
): DiffResult {
  const oldEntries = oldAnalysis.resourceEntries(includeMeta);
  const newEntries = newAnalysis.resourceEntries(includeMeta);
  const classes = classChanges(oldAnalysis, newAnalysis);
  const resources = resourceChanges(oldEntries, newEntries, detectRenames);
  const oldResources = resourceTotals(oldEntries);
  const newResources = resourceTotals(newEntries);
  const oldClassBytes = oldAnalysis.totalClassBytes();
  const newClassBytes = newAnalysis.totalClassBytes();
  const oldClassCompressed = oldAnalysis.totalClassCompressedBytes();
  const newClassCompressed = newAnalysis.totalClassCompressedBytes();

  const summary: Record<string, number> = {
    old_apk_size: oldAnalysis.fileSize,
    new_apk_size: newAnalysis.fileSize,
    apk_size_delta: newAnalysis.fileSize - oldAnalysis.fileSize,
    old_class_bytes: oldClassBytes,
    new_class_bytes: newClassBytes,
    class_bytes_delta: newClassBytes - oldClassBytes,
    old_class_compressed: oldClassCompressed,
    new_class_compressed: newClassCompressed,
    class_compressed_delta: newClassCompressed - oldClassCompressed,
    old_resource_bytes: oldResources.bytes,
    new_resource_bytes: newResources.bytes,
    old_resource_compressed: oldResources.compressed,
    new_resource_compressed: newResources.compressed,
    class_count_old: oldAnalysis.classes.size,
    class_count_new: newAnalysis.classes.size,
    class_added: count(classes, ADDED),
    class_deleted: count(classes, DELETED),
    class_modified: count(classes, MODIFIED),
    resource_added: count(resources, ADDED),
    resource_deleted: count(resources, DELETED),
    resource_modified: count(resources, MODIFIED),
    resource_renamed: count(resources, RENAMED),
    dex_unattributed_old: oldAnalysis.unattributedDexBytes(),
    dex_unattributed_new: newAnalysis.unattributedDexBytes(),
    resource_bytes_delta: newResources.bytes - oldResources.bytes,
    resource_compressed_delta: newResources.compressed - oldResources.compressed,
  };

  return new DiffResult(oldAnalysis, newAnalysis, classes, resources, summary);
}
