import { readFileSync } from 'node:fs';
import { inflateRawSync } from 'node:zlib';

/** One central-directory entry of a ZIP archive. */
export interface ZipEntry {
  name: string;
  compressedSize: number;
  fileSize: number;
  crc: number;
  method: number;
  localHeaderOffset: number;
}

const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;

/**
 * Minimal ZIP reader used by the APK analyser.
 *
 * Node has no built-in ZIP API, so this reads the end-of-central-directory record, walks the
 * central directory (where sizes and CRCs live) and inflates entries with zlib. Stored and
 * deflated entries are supported, which covers APKs; ZIP64 archives are rejected.
 */
export class ZipArchive {
  private readonly data: Buffer;
  private readonly entryList: ZipEntry[] = [];
  private readonly byName = new Map<string, ZipEntry>();

  constructor(path: string) {
    this.data = readFileSync(path);
    this.parseCentralDirectory();
  }

  entries(): ZipEntry[] {
    return this.entryList;
  }

  getEntry(name: string): ZipEntry | undefined {
    return this.byName.get(name);
  }

  /** Decompress (or copy) the content of one entry. */
  read(entry: ZipEntry): Buffer {
    const offset = entry.localHeaderOffset;
    if (offset < 0 || offset + 30 > this.data.length) {
      throw new Error(`local header out of bounds for ${entry.name}`);
    }
    if (this.data.readUInt32LE(offset) !== LOCAL_SIGNATURE) {
      throw new Error(`bad local header for ${entry.name}`);
    }
    const nameLength = this.data.readUInt16LE(offset + 26);
    const extraLength = this.data.readUInt16LE(offset + 28);
    const start = offset + 30 + nameLength + extraLength;
    const end = start + entry.compressedSize;
    if (end > this.data.length || end < start) {
      throw new Error(`entry data out of bounds for ${entry.name}`);
    }
    const raw = this.data.subarray(start, end);
    if (entry.method === 0) {
      return raw;
    }
    if (entry.method === 8) {
      return inflateRawSync(raw);
    }
    throw new Error(`unsupported ZIP compression method ${entry.method} for ${entry.name}`);
  }

  private parseCentralDirectory(): void {
    let eocd = -1;
    const minimum = Math.max(0, this.data.length - 22 - 0xffff);
    for (let i = this.data.length - 22; i >= minimum; i--) {
      if (this.data.readUInt32LE(i) === EOCD_SIGNATURE) {
        eocd = i;
        break;
      }
    }
    if (eocd < 0) {
      throw new Error('not a ZIP archive');
    }
    const totalEntries = this.data.readUInt16LE(eocd + 10);
    const centralOffset = this.data.readUInt32LE(eocd + 16);
    if (totalEntries === 0xffff || centralOffset === 0xffffffff) {
      throw new Error('ZIP64 archives are not supported');
    }

    let pos = centralOffset;
    for (let i = 0; i < totalEntries; i++) {
      if (pos + 46 > this.data.length || this.data.readUInt32LE(pos) !== CENTRAL_SIGNATURE) {
        throw new Error('bad central directory entry');
      }
      const flags = this.data.readUInt16LE(pos + 8);
      const method = this.data.readUInt16LE(pos + 10);
      const crc = this.data.readUInt32LE(pos + 16);
      const compressedSize = this.data.readUInt32LE(pos + 20);
      const fileSize = this.data.readUInt32LE(pos + 24);
      const nameLength = this.data.readUInt16LE(pos + 28);
      const extraLength = this.data.readUInt16LE(pos + 30);
      const commentLength = this.data.readUInt16LE(pos + 32);
      const localHeaderOffset = this.data.readUInt32LE(pos + 42);
      const nameStart = pos + 46;
      const nameEnd = nameStart + nameLength;
      if (nameEnd > this.data.length) {
        throw new Error('central directory name out of bounds');
      }
      const name = this.data.toString(
        (flags & 0x0800) !== 0 ? 'utf8' : 'latin1',
        nameStart,
        nameEnd,
      );
      const entry: ZipEntry = {
        name,
        compressedSize,
        fileSize,
        crc,
        method,
        localHeaderOffset,
      };
      this.entryList.push(entry);
      this.byName.set(name, entry);
      pos = nameEnd + extraLength + commentLength;
    }
  }
}
