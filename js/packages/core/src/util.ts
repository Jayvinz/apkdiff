import { createHash } from 'node:crypto';

/**
 * Where the bytes attributed to a single class came from.
 *
 * The fields are mutable because the DEX parser fills one instance per class while it
 * walks the file.
 */
export class SizeBreakdown {
  defItem = 0;
  classData = 0;
  code = 0;
  debugInfo = 0;
  annotations = 0;
  staticValues = 0;
  identifiers = 0;
  strings = 0;
  typeLists = 0;

  /** Key order matches the JSON report and the Python implementation. */
  asMap(): Record<string, number> {
    return {
      def_item: this.defItem,
      class_data: this.classData,
      code: this.code,
      debug_info: this.debugInfo,
      annotations: this.annotations,
      static_values: this.staticValues,
      identifiers: this.identifiers,
      strings: this.strings,
      type_lists: this.typeLists,
    };
  }

  total(): number {
    return this.defItem + this.classData + this.code + this.debugInfo
      + this.annotations + this.staticValues + this.identifiers
      + this.strings + this.typeLists;
  }

  plus(other: SizeBreakdown): SizeBreakdown {
    const sum = new SizeBreakdown();
    sum.defItem = this.defItem + other.defItem;
    sum.classData = this.classData + other.classData;
    sum.code = this.code + other.code;
    sum.debugInfo = this.debugInfo + other.debugInfo;
    sum.annotations = this.annotations + other.annotations;
    sum.staticValues = this.staticValues + other.staticValues;
    sum.identifiers = this.identifiers + other.identifiers;
    sum.strings = this.strings + other.strings;
    sum.typeLists = this.typeLists + other.typeLists;
    return sum;
  }
}

/**
 * A number whose JSON rendering keeps a fixed number of decimals (e.g. 0.0, 12.3).
 *
 * JavaScript numbers cannot distinguish 0 from 0.0, but Python/Kotlin reports render
 * floats with a fractional part. Detail values use this wrapper so JSON output stays
 * byte-identical; `valueOf()`/`toString()` make it usable as a number by consumers.
 */
export class FixedDecimal {
  constructor(public readonly text: string) {
  }

  valueOf(): number {
    return Number(this.text);
  }

  toString(): string {
    return this.text;
  }
}

/**
 * Round a double to `places` decimals using round-half-even on its exact binary value,
 * matching Python's `round()` / Java's BigDecimal formatting.
 */
export function formatFixed(value: number, places: number): string {
  if (!Number.isFinite(value)) {
    return 'null';
  }
  if (value === 0) {
    return places > 0 ? `0.${'0'.repeat(places)}` : '0';
  }
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, value, false);
  const bits = view.getBigUint64(0, false);
  const negative = (bits & (1n << 63n)) !== 0n;
  const exponentBits = Number((bits >> 52n) & 0x7ffn);
  let mantissa = bits & ((1n << 52n) - 1n);
  let exponent: number;
  if (exponentBits === 0) {
    exponent = -1074;
  } else {
    mantissa |= 1n << 52n;
    exponent = exponentBits - 1023 - 52;
  }
  const scale = 10n ** BigInt(places);
  let numerator = mantissa * scale;
  let denominator = 1n;
  if (exponent >= 0) {
    numerator *= 1n << BigInt(exponent);
  } else {
    denominator = 1n << BigInt(-exponent);
  }
  let quotient = numerator / denominator;
  const remainder = numerator % denominator;
  const twice = remainder * 2n;
  if (twice > denominator || (twice === denominator && (quotient & 1n) === 1n)) {
    quotient += 1n;
  }
  const digits = quotient.toString().padStart(places + 1, '0');
  const whole = digits.slice(0, digits.length - places) || '0';
  const fraction = places > 0 ? `.${digits.slice(digits.length - places)}` : '';
  return `${negative ? '-' : ''}${whole}${fraction}`;
}

/** A FixedDecimal value, for use in report details. */
export function fixedDecimal(value: number, places: number): FixedDecimal {
  return new FixedDecimal(formatFixed(value, places));
}

function human(num: number | null, signed: boolean): string {
  if (num === null) {
    return '-';
  }
  let sign: string;
  if (signed && num > 0) {
    sign = '+';
  } else if (num < 0) {
    sign = '-';
  } else {
    sign = '';
  }
  let n = Math.abs(num) / 1024.0;
  const units = ['KB', 'MB', 'GB', 'TB'];
  for (const unit of units) {
    if (n < 1024.0 || unit === 'TB') {
      return `${sign}${formatFixed(n, 2)} ${unit}`;
    }
    n /= 1024.0;
  }
  return `${sign}${formatFixed(n, 2)} TB`;
}

/** Human readable size, e.g. 0.25 KB / 7.51 KB / 90.85 KB. */
export function humanSize(num: number | null): string {
  return human(num, false);
}

/** Signed human readable size change, e.g. +7.51 KB / -0.25 KB. */
export function humanDelta(num: number | null): string {
  return human(num, true);
}

/** Code-point-ish stable ordering used for class names and map keys. */
export function compareStrings(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Combine two optional warning strings with the parser's " | " separator. */
export function joinNonEmpty(first: string, second: string): string {
  if (first === '') {
    return second;
  }
  if (second === '') {
    return first;
  }
  return `${first} | ${second}`;
}

/** Extract a printable message from a thrown value. */
export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** SHA-256 of the given bytes, lowercase hex. */
export function sha256Hex(data: Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}
