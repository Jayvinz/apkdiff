import { readFileSync } from 'node:fs';
import { descriptorToClassName } from './dex';
import { messageOf } from './util';

/**
 * Reads a ProGuard / R8 `mapping.txt` and resolves obfuscated class names back to business
 * names. Only class-level mappings are parsed.
 *
 * A missing mapping file is fine; names from the DEX are shown unchanged.
 */
export class Mapping {
  constructor(
    public readonly path: string,
    /** obfuscated dotted name -> original dotted name */
    public readonly classNames: Map<string, string> = new Map(),
    public readonly warnings: string[] = [],
  ) {
  }

  /**
   * Resolve a dotted obfuscated class name, longest-prefix safe.
   * Falls back to the input when no mapping exists.
   */
  originalName(obfuscated: string): string {
    let name = obfuscated.trim();
    const direct = this.classNames.get(name);
    if (direct !== undefined) {
      return direct;
    }
    // Some R8 versions emit array-ish or generic suffixes; strip them.
    for (const suffix of ['[]', '...']) {
      while (name.endsWith(suffix)) {
        name = name.substring(0, name.length - suffix.length);
      }
    }
    return this.classNames.get(name) ?? obfuscated;
  }

  /** 'La/b/c;' to original fully-qualified class name. */
  deobfuscateDescriptor(descriptor: string): string {
    return this.originalName(descriptorToClassName(descriptor));
  }

  static parse(path: string): Mapping {
    const mapping = new Mapping(path);
    let text: string;
    try {
      text = readFileSync(path, 'utf8');
    } catch (error) {
      mapping.warnings.push(
        `cannot read mapping file: ${messageOf(error)}`);
      return mapping;
    }

    const pattern = /^\s*(\S+)\s+->\s+(\S+):\s*$/;
    const lines = text.split(/\r\n|\n|\r/);
    lines.forEach((line, index) => {
      // Only class mappings match this shape:
      //   com.shop.ui.MainActivity -> a.b:
      // Comments and method/field lines are skipped.
      const match = pattern.exec(line);
      if (match === null) {
        return;
      }
      const original = match[1];
      const obfuscated = match[2];
      if (original.startsWith('#') || obfuscated.startsWith('#')) {
        return;
      }
      const previous = mapping.classNames.get(obfuscated);
      if (previous !== undefined && previous !== original) {
        mapping.warnings.push(
          `line ${index + 1}: duplicate obfuscated name '${obfuscated}'`);
      }
      mapping.classNames.set(obfuscated, original);
    });
    return mapping;
  }
}

/** Load a mapping file, returning an empty Mapping when path is null or blank. */
export function loadMapping(path: string | null | undefined): Mapping {
  if (path === null || path === undefined || path.trim() === '') {
    return new Mapping('');
  }
  return Mapping.parse(path);
}
