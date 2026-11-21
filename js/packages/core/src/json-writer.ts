import { FixedDecimal } from './util';

/**
 * Minimal deterministic JSON writer (pretty printed, UTF-8 raw, Python-compatible layout).
 *
 * Plain objects are used as ordered maps; JavaScript preserves insertion order for the
 * non-numeric string keys used by the report.
 */
export function writeJsonValue(value: unknown, indent = 2): string {
  const out: string[] = [];
  appendValue(out, value, 0, indent);
  return out.join('');
}

function appendValue(out: string[], value: unknown, level: number, indent: number): void {
  if (value === null || value === undefined) {
    out.push('null');
    return;
  }
  if (typeof value === 'boolean') {
    out.push(value ? 'true' : 'false');
    return;
  }
  if (typeof value === 'number') {
    out.push(numberToString(value));
    return;
  }
  if (typeof value === 'string') {
    out.push(quote(value));
    return;
  }
  if (value instanceof FixedDecimal) {
    out.push(value.text);
    return;
  }
  if (Array.isArray(value)) {
    appendArray(out, value, level, indent);
    return;
  }
  if (typeof value === 'object') {
    appendObject(out, value as Record<string, unknown>, level, indent);
    return;
  }
  out.push(quote(String(value)));
}

function appendObject(
  out: string[],
  value: Record<string, unknown>,
  level: number,
  indent: number,
): void {
  const keys = Object.keys(value);
  if (keys.length === 0) {
    out.push('{}');
    return;
  }
  out.push('{\n');
  keys.forEach((key, index) => {
    out.push(' '.repeat(indent * (level + 1)));
    out.push(quote(key));
    out.push(': ');
    appendValue(out, value[key], level + 1, indent);
    if (index !== keys.length - 1) {
      out.push(',');
    }
    out.push('\n');
  });
  out.push(' '.repeat(indent * level));
  out.push('}');
}

function appendArray(out: string[], value: unknown[], level: number, indent: number): void {
  if (value.length === 0) {
    out.push('[]');
    return;
  }
  out.push('[\n');
  value.forEach((item, index) => {
    out.push(' '.repeat(indent * (level + 1)));
    appendValue(out, item, level + 1, indent);
    if (index !== value.length - 1) {
      out.push(',');
    }
    out.push('\n');
  });
  out.push(' '.repeat(indent * level));
  out.push(']');
}

function numberToString(value: number): string {
  if (!Number.isFinite(value)) {
    return 'null';
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  // Python/Kotlin JSON render whole doubles as e.g. 0.0 rather than 0.
  if (value === Math.trunc(value)) {
    return `${Math.trunc(value)}.0`;
  }
  return String(value);
}

function quote(value: string): string {
  let out = '"';
  for (let i = 0; i < value.length; i++) {
    const ch = value.charCodeAt(i);
    switch (ch) {
      case 0x22:
        out += '\\"';
        break;
      case 0x5c:
        out += '\\\\';
        break;
      case 0x08:
        out += '\\b';
        break;
      case 0x0c:
        out += '\\f';
        break;
      case 0x0a:
        out += '\\n';
        break;
      case 0x0d:
        out += '\\r';
        break;
      case 0x09:
        out += '\\t';
        break;
      default:
        if (ch < 0x20) {
          out += `\\u${ch.toString(16).padStart(4, '0')}`;
        } else {
          out += value[i];
        }
        break;
    }
  }
  return `${out}"`;
}
