import { createHash } from 'node:crypto';
import { SizeBreakdown, compareStrings, messageOf } from './util';

/** Raised when a dex structure cannot be parsed. */
export class DexException extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DexException';
  }
}

// ---------------------------------------------------------------------------
// low level readers
// ---------------------------------------------------------------------------

export function readU1(data: Buffer, off: number): number {
  if (off < 0 || off >= data.length) {
    throw new DexException(`u1 read out of bounds at 0x${off.toString(16)}`);
  }
  return data[off];
}

export function readU2(data: Buffer, off: number): number {
  if (off < 0 || off + 2 > data.length) {
    throw new DexException(`u2 read out of bounds at 0x${off.toString(16)}`);
  }
  return data.readUInt16LE(off);
}

export function readU4(data: Buffer, off: number): number {
  if (off < 0 || off + 4 > data.length) {
    throw new DexException(`u4 read out of bounds at 0x${off.toString(16)}`);
  }
  return data.readUInt32LE(off);
}

/** Read an unsigned LEB128 value; returns [value, new offset]. */
export function uleb128(data: Buffer, off: number): [number, number] {
  let result = 0;
  let shift = 0;
  let pos = off;
  while (true) {
    const b = readU1(data, pos);
    pos++;
    result += (b & 0x7f) * 2 ** shift;
    if ((b & 0x80) === 0) {
      return [result, pos];
    }
    shift += 7;
    if (shift > 35) {
      throw new DexException('uleb128 too long');
    }
  }
}

/** Read a signed LEB128 value; returns [value, new offset]. */
export function sleb128(data: Buffer, off: number): [number, number] {
  let result = 0;
  let shift = 0;
  let pos = off;
  while (true) {
    const b = readU1(data, pos);
    pos++;
    result += (b & 0x7f) * 2 ** shift;
    shift += 7;
    if ((b & 0x80) === 0) {
      if ((b & 0x40) !== 0) {
        result -= 2 ** shift;
      }
      return [result, pos];
    }
    if (shift > 63) {
      throw new DexException('sleb128 too long');
    }
  }
}

/**
 * Decode DEX MUTF-8, folding surrogate pairs back into codepoints.
 *
 * MUTF-8 encodes NUL as 0xC0 0x80 and keeps surrogate halves separate; this normalises the
 * result to standard JavaScript strings.
 */
export function decodeMutf8(raw: Buffer): string {
  const units: number[] = [];
  let i = 0;
  while (i < raw.length) {
    const b = raw[i];
    if (b === 0) {
      break;
    }
    if (b < 0x80) {
      units.push(b);
      i += 1;
    } else if ((b & 0xe0) === 0xc0) {
      if (i + 1 >= raw.length) {
        break;
      }
      units.push(((b & 0x1f) << 6) | (raw[i + 1] & 0x3f));
      i += 2;
    } else if ((b & 0xf0) === 0xe0) {
      if (i + 2 >= raw.length) {
        break;
      }
      units.push(((b & 0x0f) << 12) | ((raw[i + 1] & 0x3f) << 6) | (raw[i + 2] & 0x3f));
      i += 3;
    } else {
      units.push(0xfffd);
      i += 1;
    }
  }

  let out = '';
  let j = 0;
  while (j < units.length) {
    const u = units[j];
    if (u >= 0xd800 && u <= 0xdbff && j + 1 < units.length
      && units[j + 1] >= 0xdc00 && units[j + 1] <= 0xdfff) {
      const low = units[j + 1];
      const cp = 0x10000 + ((u - 0xd800) << 10) + (low - 0xdc00);
      out += String.fromCodePoint(cp);
      j += 2;
    } else {
      out += String.fromCharCode(u <= 0x10ffff ? u : 0xfffd);
      j += 1;
    }
  }
  return out;
}

/** 'Lcom/foo/Bar;' to 'com.foo.Bar'; '$' is kept for inner classes. */
export function descriptorToClassName(desc: string): string {
  if (desc.startsWith('L') && desc.endsWith(';')) {
    return desc.substring(1, desc.length - 1).replace(/\//g, '.');
  }
  return desc;
}

// ---------------------------------------------------------------------------
// data model
// ---------------------------------------------------------------------------

export class DexClass {
  constructor(
    public readonly name: string,
    public readonly dexName: string,
    public readonly size: number,
    public readonly breakdown: SizeBreakdown,
    public readonly contentHash: string,
    public readonly methods: number,
    public readonly fields: number,
    public readonly partial: boolean,
    public readonly warning: string,
    public readonly semanticParts: string[],
  ) {
  }
}

export class DexAnalysis {
  readonly classes: DexClass[] = [];
  unattributed = 0;
  readonly warnings: string[] = [];

  constructor(
    public readonly path: string,
    public readonly fileSize: number,
  ) {
  }
}

interface TypeList {
  indices: number[];
  size: number;
}

interface AnnotationSet {
  end: number;
  items: number[];
}

interface AnnotationDirectory {
  size: number;
  setOffsets: number[];
}

interface AnnotationTotal {
  size: number;
  offsets: number[];
}

interface DebugInfo {
  end: number;
  names: number[];
}

interface CodeItem {
  size: number;
  debugOff: number;
  insnsSize: number;
}

interface ClassData {
  size: number;
  fields: Array<[number, number]>;
  methods: Array<[number, number, number]>;
}

class ClassRecord {
  readonly strings = new Set<number>();
  readonly types = new Set<number>();
  readonly fields = new Set<number>();
  readonly methods = new Set<number>();
  readonly protos = new Set<number>();
  readonly breakdown = new SizeBreakdown();
  readonly semantic: string[] = [];
  partial = false;
  warning = '';
  methodCount = 0;
  fieldCount = 0;

  constructor(readonly descriptor: string) {
    this.breakdown.defItem = 32;
  }
}

// ---------------------------------------------------------------------------
// parser
// ---------------------------------------------------------------------------

/**
 * DEX parser: attributes every byte of a dex file to a concrete class.
 *
 * Bytes that clearly belong to a class are charged directly. Shared tables are charged to
 * the first class (in descriptor order) that references an entry, keeping the result
 * deterministic; everything left over lands in `unattributed`, so
 * `sum(class sizes) + unattributed == dex file size`.
 */
export class DexFile {
  private readonly stringIdsSize: number;
  private readonly stringIdsOff: number;
  private readonly typeIdsSize: number;
  private readonly typeIdsOff: number;
  private readonly protoIdsSize: number;
  private readonly protoIdsOff: number;
  private readonly fieldIdsSize: number;
  private readonly fieldIdsOff: number;
  private readonly methodIdsSize: number;
  private readonly methodIdsOff: number;
  private readonly classDefsSize: number;
  private readonly classDefsOff: number;

  private readonly stringCache = new Map<number, string>();
  private readonly stringBlobSizes = new Map<number, number>();
  private readonly parseWarnings: string[] = [];

  constructor(
    private readonly data: Buffer,
    private readonly dexName = 'classes.dex',
  ) {
    const magic = data.length >= 4 ? data.subarray(0, 4).toString('latin1') : '';
    if (data.length < 112 || magic !== 'dex\n') {
      throw new DexException(`${dexName}: not a DEX file`);
    }
    const endian = readU4(data, 0x28);
    if (endian !== 0x12345678) {
      throw new DexException(`${dexName}: unsupported endian tag 0x${endian.toString(16)}`);
    }

    this.stringIdsSize = readU4(data, 0x38);
    this.stringIdsOff = readU4(data, 0x3c);
    this.typeIdsSize = readU4(data, 0x40);
    this.typeIdsOff = readU4(data, 0x44);
    this.protoIdsSize = readU4(data, 0x48);
    this.protoIdsOff = readU4(data, 0x4c);
    this.fieldIdsSize = readU4(data, 0x50);
    this.fieldIdsOff = readU4(data, 0x54);
    this.methodIdsSize = readU4(data, 0x58);
    this.methodIdsOff = readU4(data, 0x5c);
    this.classDefsSize = readU4(data, 0x60);
    this.classDefsOff = readU4(data, 0x64);
  }

  // -- string / type helpers ------------------------------------------------

  string(idx: number): string {
    const cached = this.stringCache.get(idx);
    if (cached !== undefined) {
      return cached;
    }
    if (idx < 0 || idx >= this.stringIdsSize) {
      throw new DexException(`string index ${idx} out of range`);
    }
    const off = readU4(this.data, this.stringIdsOff + 4 * idx);
    const valueStart = uleb128(this.data, off)[1];
    let pos = valueStart;
    while (readU1(this.data, pos) !== 0) {
      pos++;
    }
    this.stringBlobSizes.set(idx, pos + 1 - off);
    const value = decodeMutf8(this.data.subarray(valueStart, pos));
    this.stringCache.set(idx, value);
    return value;
  }

  stringBlobSize(idx: number): number {
    if (!this.stringBlobSizes.has(idx)) {
      this.string(idx);
    }
    return this.stringBlobSizes.get(idx) ?? 0;
  }

  typeDescriptor(typeIdx: number): string {
    if (typeIdx < 0 || typeIdx >= this.typeIdsSize) {
      throw new DexException(`type index ${typeIdx} out of range`);
    }
    return this.string(readU4(this.data, this.typeIdsOff + 4 * typeIdx));
  }

  typeStringIdx(typeIdx: number): number | null {
    if (typeIdx < 0 || typeIdx >= this.typeIdsSize) {
      return null;
    }
    return readU4(this.data, this.typeIdsOff + 4 * typeIdx);
  }

  fieldNameIdx(fieldIdx: number): number | null {
    if (fieldIdx < 0 || fieldIdx >= this.fieldIdsSize) {
      return null;
    }
    return readU4(this.data, this.fieldIdsOff + 8 * fieldIdx + 4);
  }

  fieldTypeIdx(fieldIdx: number): number | null {
    if (fieldIdx < 0 || fieldIdx >= this.fieldIdsSize) {
      return null;
    }
    // field_id_item: class_idx(u2) type_idx(u2) name_idx(u4)
    return readU2(this.data, this.fieldIdsOff + 8 * fieldIdx + 2);
  }

  methodNameIdx(methodIdx: number): number | null {
    if (methodIdx < 0 || methodIdx >= this.methodIdsSize) {
      return null;
    }
    return readU4(this.data, this.methodIdsOff + 8 * methodIdx + 4);
  }

  methodProtoIdx(methodIdx: number): number | null {
    if (methodIdx < 0 || methodIdx >= this.methodIdsSize) {
      return null;
    }
    // method_id_item: class_idx(u2) proto_idx(u2) name_idx(u4)
    return readU2(this.data, this.methodIdsOff + 8 * methodIdx + 2);
  }

  /** String indices owned by a proto_id (shorty + return + param types). */
  protoStringIndices(protoIdx: number): number[] {
    if (protoIdx < 0 || protoIdx >= this.protoIdsSize) {
      return [];
    }
    const base = this.protoIdsOff + 12 * protoIdx;
    const out: number[] = [readU4(this.data, base)]; // shorty_idx
    // The Python implementation used `type_string_idx(...) or -1`, which drops a valid
    // index of 0. Keep that exact behaviour so byte attribution matches upstream.
    const returnType = this.typeStringIdx(readU4(this.data, base + 4));
    if (returnType !== null && returnType !== 0) {
      out.push(returnType);
    }
    const paramsOff = readU4(this.data, base + 8);
    if (paramsOff !== 0) {
      const count = Math.min(readU4(this.data, paramsOff), 4096);
      for (let i = 0; i < count; i++) {
        const param = this.typeStringIdx(readU2(this.data, paramsOff + 4 + 2 * i));
        if (param !== null && param !== 0) {
          out.push(param);
        }
      }
    }
    return out;
  }

  /** '(Ljava/lang/String;)I' style signature for a proto_id. */
  protoDescriptor(protoIdx: number): string {
    if (protoIdx < 0 || protoIdx >= this.protoIdsSize) {
      return '<?>';
    }
    const base = this.protoIdsOff + 12 * protoIdx;
    try {
      const returnType = this.typeDescriptor(readU4(this.data, base + 4));
      const paramsOff = readU4(this.data, base + 8);
      let params = '';
      if (paramsOff !== 0) {
        const count = Math.min(readU4(this.data, paramsOff), 4096);
        for (let i = 0; i < count; i++) {
          params += this.typeDescriptor(readU2(this.data, paramsOff + 4 + 2 * i));
        }
      }
      return `(${params})${returnType}`;
    } catch {
      return '<?>';
    }
  }

  typeListIndices(off: number): TypeList {
    if (off === 0) {
      return { indices: [], size: 0 };
    }
    const count = Math.min(readU4(this.data, off), 4096);
    const indices: number[] = [];
    for (let i = 0; i < count; i++) {
      indices.push(readU2(this.data, off + 4 + 2 * i));
    }
    return { indices, size: 4 + 2 * count };
  }

  // -- structural size helpers ---------------------------------------------

  private isPrimitiveValue(valueType: number): boolean {
    switch (valueType) {
      case 0x00:
      case 0x02:
      case 0x03:
      case 0x04:
      case 0x05:
      case 0x10:
      case 0x11:
        return true;
      default:
        return false;
    }
  }

  encodedValueEnd(off: number, depth: number): number {
    if (depth > 32) {
      throw new DexException('encoded_value nesting too deep');
    }
    const header = readU1(this.data, off);
    const valueType = header & 0x1f;
    const arg = header >>> 5;
    let pos = off + 1;

    if (valueType === 0x1f) { // BOOLEAN: value is in value_arg, no payload
      return pos;
    }
    if (this.isPrimitiveValue(valueType)) {
      return pos + arg + 1;
    }
    if (valueType >= 0x15 && valueType <= 0x1b) {
      // Index-valued types use a fixed width of (value_arg + 1) little-endian bytes rather
      // than uleb128; reading them as uleb128 desynchronises the walker on indices >= 128.
      return pos + arg + 1;
    }
    if (valueType === 0x1c) { // ARRAY
      const count = uleb128(this.data, pos);
      pos = count[1];
      for (let i = 0; i < Math.min(count[0], 65536); i++) {
        pos = this.encodedValueEnd(pos, depth + 1);
      }
      return pos;
    }
    if (valueType === 0x1d) { // ANNOTATION
      const type = uleb128(this.data, pos);
      pos = type[1];
      const count = uleb128(this.data, pos);
      pos = count[1];
      for (let i = 0; i < Math.min(count[0], 65536); i++) {
        const name = uleb128(this.data, pos);
        pos = name[1];
        pos = this.encodedValueEnd(pos, depth + 1);
      }
      return pos;
    }
    if (valueType === 0x1e) { // NULL
      return pos;
    }
    throw new DexException(`unknown encoded_value type 0x${valueType.toString(16)}`);
  }

  encodedArrayEnd(off: number): number {
    const count = uleb128(this.data, off);
    let pos = count[1];
    for (let i = 0; i < Math.min(count[0], 65536); i++) {
      pos = this.encodedValueEnd(pos, 0);
    }
    return pos;
  }

  annotationItemEnd(off: number): number {
    let pos = off + 1; // visibility byte
    const type = uleb128(this.data, pos);
    pos = type[1];
    const count = uleb128(this.data, pos);
    pos = count[1];
    for (let i = 0; i < Math.min(count[0], 65536); i++) {
      const name = uleb128(this.data, pos);
      pos = name[1];
      pos = this.encodedValueEnd(pos, 0);
    }
    return pos;
  }

  annotationSetEnd(off: number): AnnotationSet {
    const count = readU4(this.data, off);
    let pos = off + 4;
    const items: number[] = [];
    for (let i = 0; i < Math.min(count, 65536); i++) {
      items.push(readU4(this.data, pos));
      pos += 4;
    }
    return { end: pos, items };
  }

  annotationDirectorySize(off: number): AnnotationDirectory {
    const classAnnotationsOff = readU4(this.data, off);
    const fieldsSize = readU4(this.data, off + 4);
    const methodsSize = readU4(this.data, off + 8);
    const paramsSize = readU4(this.data, off + 12);
    const end = off + 16 + 8 * (fieldsSize + methodsSize + paramsSize);
    const setOffsets: number[] = [];
    if (classAnnotationsOff !== 0) {
      setOffsets.push(classAnnotationsOff);
    }
    const entryBase = off + 16;
    for (let i = 0; i < fieldsSize + methodsSize + paramsSize; i++) {
      // Each entry is 8 bytes: (field/method/param) index + annotations offset.
      // The set offset is the second u4, not the first.
      setOffsets.push(readU4(this.data, entryBase + 8 * i + 4));
    }
    return { size: end - off, setOffsets };
  }

  /**
   * Total bytes of an annotation directory and everything it points to.
   *
   * `seenSets` / `seenItems` are shared across classes so that two classes carrying the
   * same annotation do not double-count its bytes.
   */
  annotationsTotalSize(
    off: number,
    seenSets: Set<number>,
    seenItems: Set<number>,
  ): AnnotationTotal {
    const directory = this.annotationDirectorySize(off);
    let total = directory.size;
    const annotationOffsets: number[] = [];
    const localOffsets = new Set<number>();
    for (const setOff of directory.setOffsets) {
      if (setOff === 0 || seenSets.has(setOff)) {
        continue;
      }
      seenSets.add(setOff);
      const set = this.annotationSetEnd(setOff);
      total += set.end - setOff;
      for (const itemOff of set.items) {
        if (!localOffsets.has(itemOff)) {
          localOffsets.add(itemOff);
          annotationOffsets.push(itemOff);
        }
      }
    }
    for (const itemOff of annotationOffsets) {
      if (seenItems.has(itemOff)) {
        continue;
      }
      seenItems.add(itemOff);
      total += this.annotationItemEnd(itemOff) - itemOff;
    }
    return { size: total, offsets: annotationOffsets };
  }

  debugInfoEnd(off: number): DebugInfo {
    const lineStart = uleb128(this.data, off);
    let pos = lineStart[1];
    const params = uleb128(this.data, pos);
    pos = params[1];
    const names: number[] = [];
    for (let i = 0; i < Math.min(params[0], 4096); i++) {
      const nameIdx = uleb128(this.data, pos);
      pos = nameIdx[1];
      if (nameIdx[0] !== 0) {
        names.push(nameIdx[0] - 1);
      }
    }
    while (true) {
      const opcode = readU1(this.data, pos);
      pos++;
      switch (opcode) {
        case 0x00: // END_SEQUENCE
          return { end: pos, names };
        case 0x01: // ADVANCE_PC
          pos = uleb128(this.data, pos)[1];
          break;
        case 0x02: // ADVANCE_LINE
          pos = sleb128(this.data, pos)[1];
          break;
        case 0x03: { // START_LOCAL
          pos = uleb128(this.data, pos)[1];
          const nameIdx = uleb128(this.data, pos);
          pos = nameIdx[1];
          if (nameIdx[0] !== 0) {
            names.push(nameIdx[0] - 1);
          }
          pos = uleb128(this.data, pos)[1];
          break;
        }
        case 0x04: { // START_LOCAL_EXTENDED
          pos = uleb128(this.data, pos)[1];
          const nameIdx = uleb128(this.data, pos);
          pos = nameIdx[1];
          if (nameIdx[0] !== 0) {
            names.push(nameIdx[0] - 1);
          }
          pos = uleb128(this.data, pos)[1];
          pos = uleb128(this.data, pos)[1];
          break;
        }
        case 0x05: // END_LOCAL
        case 0x06: // RESTART_LOCAL
          pos = uleb128(this.data, pos)[1];
          break;
        case 0x07: // PROLOGUE_END
        case 0x08: // EPILOGUE_BEGIN
          break;
        case 0x09: // SET_FILE
          pos = uleb128(this.data, pos)[1];
          break;
        default:
          // 0x0a..0xff are SPECIAL opcodes: the pc/line delta is encoded in the opcode
          // byte itself, so they have NO operand.
          break;
      }
    }
  }

  codeItemSize(off: number): CodeItem {
    const triesSize = readU2(this.data, off + 6);
    const debugOff = readU4(this.data, off + 8);
    const insnsSize = readU4(this.data, off + 12);
    let pos = off + 16 + 2 * insnsSize;
    if (triesSize !== 0) {
      if ((insnsSize & 1) !== 0) {
        pos += 2; // try_item starts on a 4-byte boundary
      }
      pos += 8 * triesSize;
      const handlersSize = uleb128(this.data, pos);
      pos = handlersSize[1];
      for (let i = 0; i < Math.min(handlersSize[0], 65536); i++) {
        const handled = uleb128(this.data, pos);
        pos = handled[1];
        for (let j = 0; j < Math.min(handled[0], 65536); j++) {
          pos = uleb128(this.data, pos)[1];
          pos = uleb128(this.data, pos)[1];
        }
        if (handled[0] === 0) {
          pos = uleb128(this.data, pos)[1];
        }
      }
    }
    return { size: pos - off, debugOff, insnsSize };
  }

  classDataInfo(off: number): ClassData {
    if (off === 0) {
      return { size: 0, fields: [], methods: [] };
    }
    const staticFields = uleb128(this.data, off);
    let pos = staticFields[1];
    const instanceFields = uleb128(this.data, pos);
    pos = instanceFields[1];
    const directMethods = uleb128(this.data, pos);
    pos = directMethods[1];
    const virtualMethods = uleb128(this.data, pos);
    pos = virtualMethods[1];

    const fields: Array<[number, number]> = [];
    const methods: Array<[number, number, number]> = [];

    // Each of the four lists encodes its first index as a full value and the remaining
    // ones as deltas. The delta sequence RESTARTS per list.
    let index = 0;
    for (let i = 0; i < staticFields[0]; i++) {
      const diff = uleb128(this.data, pos);
      pos = diff[1];
      const flags = uleb128(this.data, pos);
      pos = flags[1];
      index += diff[0];
      fields.push([index, flags[0]]);
    }
    index = 0;
    for (let i = 0; i < instanceFields[0]; i++) {
      const diff = uleb128(this.data, pos);
      pos = diff[1];
      const flags = uleb128(this.data, pos);
      pos = flags[1];
      index += diff[0];
      fields.push([index, flags[0]]);
    }
    index = 0;
    for (let i = 0; i < directMethods[0]; i++) {
      const diff = uleb128(this.data, pos);
      pos = diff[1];
      const flags = uleb128(this.data, pos);
      pos = flags[1];
      const codeOff = uleb128(this.data, pos);
      pos = codeOff[1];
      index += diff[0];
      methods.push([index, flags[0], codeOff[0]]);
    }
    index = 0;
    for (let i = 0; i < virtualMethods[0]; i++) {
      const diff = uleb128(this.data, pos);
      pos = diff[1];
      const flags = uleb128(this.data, pos);
      pos = flags[1];
      const codeOff = uleb128(this.data, pos);
      pos = codeOff[1];
      index += diff[0];
      methods.push([index, flags[0], codeOff[0]]);
    }
    return { size: pos - off, fields, methods };
  }

  // -- main analysis --------------------------------------------------------

  analyze(): DexAnalysis {
    const result = new DexAnalysis(this.dexName, this.data.length);

    for (let i = 0; i < this.stringIdsSize; i++) {
      try {
        this.string(i);
      } catch (error) {
        this.parseWarnings.push(`string[${i}]: ${messageOf(error)}`);
      }
    }

    const records: ClassRecord[] = [];
    const seenAnnotationSets = new Set<number>();
    const seenAnnotationItems = new Set<number>();

    for (let i = 0; i < this.classDefsSize; i++) {
      const base = this.classDefsOff + 32 * i;
      let classIdx = 0;
      let accessFlags = 0;
      let superclassIdx = 0;
      let interfacesOff = 0;
      let sourceFileIdx = 0;
      let annotationsOff = 0;
      let classDataOff = 0;
      let staticValuesOff = 0;
      let desc = '';
      try {
        classIdx = readU4(this.data, base);
        accessFlags = readU4(this.data, base + 4);
        superclassIdx = readU4(this.data, base + 8);
        interfacesOff = readU4(this.data, base + 12);
        sourceFileIdx = readU4(this.data, base + 16);
        annotationsOff = readU4(this.data, base + 20);
        classDataOff = readU4(this.data, base + 24);
        staticValuesOff = readU4(this.data, base + 28);
        desc = this.typeDescriptor(classIdx);
      } catch (error) {
        this.parseWarnings.push(`class_def[${i}]: ${messageOf(error)}`);
        continue;
      }

      const record = new ClassRecord(desc);
      record.types.add(classIdx);
      const classStringIdx = this.typeStringIdx(classIdx);
      if (classStringIdx !== null) {
        record.strings.add(classStringIdx);
      }

      // Human-readable, index-independent fingerprint parts. Raw DEX indices shift
      // whenever a class is added/removed, so hashing raw bytes would mark nearly every
      // class as "modified".
      record.semantic.push(`C:${accessFlags}:${desc}`);

      const superStringIdx = this.typeStringIdx(superclassIdx);
      if (superStringIdx !== null) {
        record.types.add(superclassIdx);
        record.strings.add(superStringIdx);
        try {
          record.semantic.push(`S:${this.typeDescriptor(superclassIdx)}`);
        } catch {
          // ignore
        }
      }

      if (interfacesOff !== 0) {
        try {
          const interfaces = this.typeListIndices(interfacesOff);
          record.breakdown.typeLists += interfaces.size;
          try {
            const descriptors = interfaces.indices
              .map((t) => this.typeDescriptor(t))
              .sort(compareStrings);
            record.semantic.push(`I:${descriptors.join(',')}`);
          } catch {
            // ignore
          }
          for (const t of interfaces.indices) {
            record.types.add(t);
            const stringIdx = this.typeStringIdx(t);
            if (stringIdx !== null) {
              record.strings.add(stringIdx);
            }
          }
        } catch (error) {
          record.partial = true;
          record.warning = `interfaces: ${messageOf(error)}`;
        }
      }

      if (sourceFileIdx < this.stringIdsSize) {
        record.strings.add(sourceFileIdx);
        try {
          record.semantic.push(`SF:${this.string(sourceFileIdx)}`);
        } catch {
          // ignore
        }
      }

      // class_data
      if (classDataOff !== 0) {
        try {
          const cd = this.classDataInfo(classDataOff);
          record.breakdown.classData += cd.size;
          record.fieldCount = cd.fields.length;
          record.methodCount = cd.methods.length;
          for (const [f, flags] of cd.fields) {
            record.fields.add(f);
            const fieldNameIdx = this.fieldNameIdx(f);
            const name = fieldNameIdx !== null ? this.string(fieldNameIdx) : '?';
            const fieldTypeIdx = this.fieldTypeIdx(f);
            const typeDesc = fieldTypeIdx !== null ? this.typeDescriptor(fieldTypeIdx) : '?';
            record.semantic.push(`F:${flags}:${name}:${typeDesc}`);
            if (fieldNameIdx !== null) {
              record.strings.add(fieldNameIdx);
            }
            if (fieldTypeIdx !== null) {
              record.types.add(fieldTypeIdx);
              const stringIdx = this.typeStringIdx(fieldTypeIdx);
              if (stringIdx !== null) {
                record.strings.add(stringIdx);
              }
            }
          }
          for (const [m, flags, codeOff] of cd.methods) {
            record.methods.add(m);
            const methodNameIdx = this.methodNameIdx(m);
            const name = methodNameIdx !== null ? this.string(methodNameIdx) : '?';
            if (methodNameIdx !== null) {
              record.strings.add(methodNameIdx);
            }
            const protoIdx = this.methodProtoIdx(m);
            const proto = protoIdx !== null ? this.protoDescriptor(protoIdx) : '?';
            let spec = `M:${flags}:${name}:${proto}`;
            if (protoIdx !== null) {
              record.protos.add(protoIdx);
              for (const s of this.protoStringIndices(protoIdx)) {
                record.strings.add(s);
              }
            }
            if (codeOff !== 0) {
              const code = this.codeItemSize(codeOff);
              record.breakdown.code += code.size;
              // insns_size (instruction count) is stable; the raw byte size includes
              // ULEB128 exception-handler indices which shift when other classes change.
              spec += `:ins=${code.insnsSize}`;
              if (code.debugOff !== 0) {
                try {
                  const debug = this.debugInfoEnd(code.debugOff);
                  record.breakdown.debugInfo += debug.end - code.debugOff;
                  const nameValues: string[] = [];
                  for (const idx of debug.names) {
                    if (idx < this.stringIdsSize) {
                      record.strings.add(idx);
                      nameValues.push(this.string(idx));
                    }
                  }
                  nameValues.sort(compareStrings);
                  spec += `:dbg=${nameValues.join(',')}`;
                } catch (error) {
                  record.partial = true;
                  record.warning = `debug_info: ${messageOf(error)}`;
                }
              }
            }
            record.semantic.push(spec);
          }
        } catch (error) {
          record.partial = true;
          record.warning = `class_data: ${messageOf(error)}`;
        }
      }

      // annotations -> also pull type indices out of the encoded values
      if (annotationsOff !== 0) {
        try {
          const annotations = this.annotationsTotalSize(
            annotationsOff, seenAnnotationSets, seenAnnotationItems);
          record.breakdown.annotations += annotations.size;
          for (const itemOff of annotations.offsets) {
            try {
              this.annotationItemEnd(itemOff);
              let pos = itemOff + 1;
              const type = uleb128(this.data, pos);
              pos = type[1];
              record.types.add(type[0]);
              const stringIdx = this.typeStringIdx(type[0]);
              if (stringIdx !== null) {
                record.strings.add(stringIdx);
              }
              try {
                record.semantic.push(`A:${this.typeDescriptor(type[0])}`);
              } catch {
                // ignore
              }
              const count = uleb128(this.data, pos);
              pos = count[1];
              for (let ai = 0; ai < Math.min(count[0], 4096); ai++) {
                const nameIdx = uleb128(this.data, pos);
                pos = nameIdx[1];
                pos = this.collectValueTypes(pos, record, 0);
              }
            } catch {
              // ignore malformed individual annotation items
            }
          }
        } catch (error) {
          record.partial = true;
          record.warning = trimSemicolonSpace(
            `${record.warning}; annotations: ${messageOf(error)}`);
        }
      }

      // static values
      if (staticValuesOff !== 0) {
        try {
          const end = this.encodedArrayEnd(staticValuesOff);
          record.breakdown.staticValues += end - staticValuesOff;
          let pos = staticValuesOff;
          const count = uleb128(this.data, pos);
          pos = count[1];
          for (let vi = 0; vi < Math.min(count[0], 4096); vi++) {
            pos = this.collectValueTypes(pos, record, 0);
          }
        } catch {
          // ignore
        }
      }

      // remove invalid indices
      for (const v of record.strings) {
        if (v < 0 || v >= this.stringIdsSize) record.strings.delete(v);
      }
      for (const v of record.types) {
        if (v < 0 || v >= this.typeIdsSize) record.types.delete(v);
      }
      for (const v of record.fields) {
        if (v < 0 || v >= this.fieldIdsSize) record.fields.delete(v);
      }
      for (const v of record.methods) {
        if (v < 0 || v >= this.methodIdsSize) record.methods.delete(v);
      }
      for (const v of record.protos) {
        if (v < 0 || v >= this.protoIdsSize) record.protos.delete(v);
      }
      records.push(record);
    }

    // === Pass 2: split shared tables / strings between classes ===
    records.sort((a, b) => compareStrings(a.descriptor, b.descriptor));

    const ownerType = new Map<number, number>();
    const ownerField = new Map<number, number>();
    const ownerMethod = new Map<number, number>();
    const ownerProto = new Map<number, number>();
    const ownerString = new Map<number, number>();

    records.forEach((record, posIdx) => {
      claim(ownerType, record.types, posIdx);
      claim(ownerField, record.fields, posIdx);
      claim(ownerMethod, record.methods, posIdx);
      claim(ownerProto, record.protos, posIdx);
      claim(ownerString, record.strings, posIdx);
    });

    const typeCounts = countOwners(ownerType);
    const fieldCounts = countOwners(ownerField);
    const methodCounts = countOwners(ownerMethod);
    const protoCounts = countOwners(ownerProto);
    const stringCounts = countOwners(ownerString);
    const stringsByOwner = new Map<number, number[]>();
    for (const [stringIdx, posIdx] of ownerString) {
      const list = stringsByOwner.get(posIdx) ?? [];
      list.push(stringIdx);
      stringsByOwner.set(posIdx, list);
    }

    records.forEach((record, posIdx) => {
      record.breakdown.identifiers +=
        4 * (typeCounts.get(posIdx) ?? 0)
        + 8 * (fieldCounts.get(posIdx) ?? 0)
        + 8 * (methodCounts.get(posIdx) ?? 0)
        + 12 * (protoCounts.get(posIdx) ?? 0)
        + 4 * (stringCounts.get(posIdx) ?? 0);
      for (const s of stringsByOwner.get(posIdx) ?? []) {
        record.breakdown.strings += this.stringBlobSize(s);
      }

      // Only source-meaningful parts go into the hash. Do NOT hash record.strings: that
      // set is the result of first-owner attribution and shifts when unrelated classes
      // change, which would re-introduce false "modified" noise.
      const digest = createHash('sha256');
      const semantic = [...record.semantic].sort(compareStrings);
      for (const part of semantic) {
        digest.update(part, 'utf8');
        digest.update(Buffer.from([0]));
      }

      result.classes.push(new DexClass(
        record.descriptor,
        this.dexName,
        record.breakdown.total(),
        record.breakdown,
        digest.digest('hex'),
        record.methodCount,
        record.fieldCount,
        record.partial,
        record.warning,
        semantic,
      ));
    });

    const attributed = result.classes.reduce((sum, cls) => sum + cls.size, 0);
    result.unattributed = Math.max(0, this.data.length - attributed);
    result.warnings.push(...this.parseWarnings);
    return result;
  }

  private collectValueTypes(off: number, record: ClassRecord, depth: number): number {
    if (depth > 32) {
      return off;
    }
    const header = readU1(this.data, off);
    const valueType = header & 0x1f;
    const arg = header >>> 5;
    let pos = off + 1;
    if (valueType === 0x1f) {
      return pos; // BOOLEAN: value is in value_arg, no payload
    }
    if (this.isPrimitiveValue(valueType)) {
      return pos + arg + 1;
    }
    if (valueType >= 0x15 && valueType <= 0x1b) {
      // Fixed-width little-endian index (value_arg + 1 bytes), matching how R8/D8 emit
      // encoded_value indices.
      const width = arg + 1;
      let value = 0;
      for (let i = 0; i < width; i++) {
        value += (this.data[pos + i] ?? 0) * 2 ** (8 * i);
      }
      pos += width;
      switch (valueType) {
        case 0x18: { // TYPE
          record.types.add(value);
          const stringIdx = this.typeStringIdx(value);
          if (stringIdx !== null) {
            record.strings.add(stringIdx);
          }
          break;
        }
        case 0x1b: // ENUM -> field
          record.fields.add(value);
          break;
        case 0x17: // STRING
          record.strings.add(value);
          break;
        default:
          break;
      }
      return pos;
    }
    if (valueType === 0x1c) {
      const count = uleb128(this.data, pos);
      pos = count[1];
      for (let i = 0; i < Math.min(count[0], 4096); i++) {
        pos = this.collectValueTypes(pos, record, depth + 1);
      }
      return pos;
    }
    if (valueType === 0x1d) {
      const type = uleb128(this.data, pos);
      pos = type[1];
      record.types.add(type[0]);
      const stringIdx = this.typeStringIdx(type[0]);
      if (stringIdx !== null) {
        record.strings.add(stringIdx);
      }
      const count = uleb128(this.data, pos);
      pos = count[1];
      for (let i = 0; i < Math.min(count[0], 4096); i++) {
        const nameIdx = uleb128(this.data, pos);
        pos = nameIdx[1];
        record.strings.add(nameIdx[0]);
        pos = this.collectValueTypes(pos, record, depth + 1);
      }
      return pos;
    }
    if (valueType === 0x1e) {
      return pos;
    }
    return pos;
  }
}

function claim(owners: Map<number, number>, items: Set<number>, posIdx: number): void {
  for (const item of items) {
    if (!owners.has(item)) {
      owners.set(item, posIdx);
    }
  }
}

function countOwners(owners: Map<number, number>): Map<number, number> {
  const counts = new Map<number, number>();
  for (const owner of owners.values()) {
    counts.set(owner, (counts.get(owner) ?? 0) + 1);
  }
  return counts;
}

function trimSemicolonSpace(value: string): string {
  let start = 0;
  let end = value.length;
  while (start < end && (value[start] === ';' || value[start] === ' ')) {
    start++;
  }
  while (end > start && (value[end - 1] === ';' || value[end - 1] === ' ')) {
    end--;
  }
  return value.substring(start, end);
}
