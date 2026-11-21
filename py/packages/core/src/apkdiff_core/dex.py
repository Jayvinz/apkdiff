"""DEX parser: attribute every byte of a dex file to a concrete class.

This is not a full dex decompiler. It answers one question:
**"How many bytes does this class cost?"**

Classes live in classes*.dex. A dex is a dense set of tables and structures with
no per-class byte count, so we compute one.

How it works:
    Some blocks clearly belong to a class (its method bytecode); other blocks are
    shared by all classes (string pool, type table).

    1. Charge class-specific blocks directly to that class.
    2. Charge shared blocks (for example a string) to the first class that
       references them. The order is fixed, so results are deterministic.
    3. Put everything else (header, padding, unreferenced strings) into
       `unattributed`.

    Therefore: sum(class bytes) + unattributed = dex file size. Tests enforce
    this invariant.

What is charged to a class?
    - class_def_item: the class record (fixed 32 bytes)
    - class_data_item: field and method declarations
    - code_item: bytecode + try/catch handlers per method
    - debug_info_item: debug info (local names, line numbers)
    - annotations on the class, fields and methods
    - static_values: static field initial values
    - referenced identifier-table and string-pool entries

Two key designs:

    [Byte attribution] The accounting described above; see analyze().
    [Semantic fingerprint] Change detection does NOT compare raw dex bytes.
    Adding or removing any class renumbers every index, changing raw bytes for
    classes whose source did not change. The fingerprint records only
    source-meaningful data: class name, superclass, interfaces, field/method
    signatures, local variable names, annotations and source file.

The size computed here is **uncompressed** dex bytes; apk.py estimates compression.
"""

from __future__ import annotations

import hashlib
import struct
from collections import Counter
from dataclasses import dataclass, field

from .util import SizeBreakdown


class DexError(Exception):
    pass


# encoded_value type tags shared by the size walker and the reference collector.
_PRIMITIVE_VALUE_TYPES = frozenset({0x00, 0x02, 0x03, 0x04, 0x05, 0x10, 0x11})
_INDEX_VALUE_TYPES = frozenset(range(0x15, 0x1C))


# ---------------------------------------------------------------------------
# Low-level helpers: byte readers.
# ---------------------------------------------------------------------------
# A dex is a byte stream. These helpers read integers at different widths:
# _u1 reads 1 byte, _u2 reads 2, _u4 reads 4.
# They raise on out-of-bounds reads instead of silently returning garbage.
# _uleb128 / _sleb128 are variable-length integers: small values use one
# byte, larger values use more. This is dex's space-saving encoding.


def _u1(data: bytes, off: int) -> int:
    if off < 0 or off >= len(data):
        raise DexError(f"u1 read out of bounds at 0x{off:x}")
    return data[off]


def _u2(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        raise DexError(f"u2 read out of bounds at 0x{off:x}")
    return struct.unpack_from("<H", data, off)[0]


def _u4(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise DexError(f"u4 read out of bounds at 0x{off:x}")
    return struct.unpack_from("<I", data, off)[0]


def _uleb128(data: bytes, off: int) -> tuple[int, int]:
    """Read an unsigned LEB128 value; returns (value, new offset).

    LEB128 uses 7 data bits per byte; the high bit means "more bytes follow".
    Small values (0-127) take one byte, larger values take more, saving space.
    """
    result = 0
    shift = 0
    while True:
        b = _u1(data, off)
        off += 1
        result |= (b & 0x7F) << shift  # Append the low 7 bits to the result.
        if not b & 0x80:  # High bit 0 means this is the final byte.
            return result, off
        shift += 7
        if shift > 35:
            raise DexError("uleb128 too long")


def _sleb128(data: bytes, off: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = _u1(data, off)
        off += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            if b & 0x40:
                result -= 1 << shift
            return result, off
        if shift > 63:
            raise DexError("sleb128 too long")


def _decode_mutf8(raw: bytes) -> str:
    """Decode DEX MUTF-8 (surrogate pairs folded back into codepoints)."""
    units: list[int] = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0:
            break
        if b < 0x80:
            units.append(b)
            i += 1
        elif b & 0xE0 == 0xC0:
            if i + 1 >= len(raw):
                break
            units.append(((b & 0x1F) << 6) | (raw[i + 1] & 0x3F))
            i += 2
        elif b & 0xF0 == 0xE0:
            if i + 2 >= len(raw):
                break
            units.append(
                ((b & 0x0F) << 12)
                | ((raw[i + 1] & 0x3F) << 6)
                | (raw[i + 2] & 0x3F)
            )
            i += 3
        else:
            units.append(0xFFFD)
            i += 1

    out: list[str] = []
    j = 0
    while j < len(units):
        u = units[j]
        if 0xD800 <= u <= 0xDBFF and j + 1 < len(units) and 0xDC00 <= units[j + 1] <= 0xDFFF:
            low = units[j + 1]
            cp = 0x10000 + ((u - 0xD800) << 10) + (low - 0xDC00)
            out.append(chr(cp))
            j += 2
        else:
            out.append(chr(u) if u <= 0x10FFFF else "\ufffd")
            j += 1
    return "".join(out)


def descriptor_to_class_name(desc: str) -> str:
    """'Lcom/foo/Bar;' -> 'com.foo.Bar'; '$' is kept for inner classes."""
    if desc.startswith("L") and desc.endswith(";"):
        return desc[1:-1].replace("/", ".")
    return desc


# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------


@dataclass
class DexClass:
    name: str  # descriptor, e.g. Lcom/foo/Bar;
    dex_name: str  # which dex file it came from
    size: int
    breakdown: SizeBreakdown
    content_hash: str
    methods: int = 0
    fields: int = 0
    partial: bool = False  # some structures could not be parsed
    warning: str = ""
    semantic_parts: list[str] = field(default_factory=list)


@dataclass
class DexAnalysis:
    path: str
    file_size: int
    classes: list[DexClass] = field(default_factory=list)
    unattributed: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


class DexFile:
    def __init__(self, data: bytes, dex_name: str = "classes.dex"):
        self.data = data
        self.dex_name = dex_name
        if len(data) < 112 or data[:4] != b"dex\n":
            raise DexError(f"{dex_name}: not a DEX file")
        self.endian = _u4(data, 0x28)
        if self.endian != 0x12345678:
            raise DexError(f"{dex_name}: unsupported endian tag 0x{self.endian:x}")

        self.string_ids_size = _u4(data, 0x38)
        self.string_ids_off = _u4(data, 0x3C)
        self.type_ids_size = _u4(data, 0x40)
        self.type_ids_off = _u4(data, 0x44)
        self.proto_ids_size = _u4(data, 0x48)
        self.proto_ids_off = _u4(data, 0x4C)
        self.field_ids_size = _u4(data, 0x50)
        self.field_ids_off = _u4(data, 0x54)
        self.method_ids_size = _u4(data, 0x58)
        self.method_ids_off = _u4(data, 0x5C)
        self.class_defs_size = _u4(data, 0x60)
        self.class_defs_off = _u4(data, 0x64)

        self._string_cache: dict[int, str] = {}
        self._string_blob_size: dict[int, int] = {}
        self._warnings: list[str] = []

    # -- string / type helpers ------------------------------------------------

    def string(self, idx: int) -> str:
        cached = self._string_cache.get(idx)
        if cached is not None:
            return cached
        if idx < 0 or idx >= self.string_ids_size:
            raise DexError(f"string index {idx} out of range")
        off = _u4(self.data, self.string_ids_off + 4 * idx)
        _size, pos = _uleb128(self.data, off)
        start = pos
        while _u1(self.data, pos) != 0:
            pos += 1
        blob_size = (pos + 1) - off
        self._string_blob_size[idx] = blob_size
        value = _decode_mutf8(self.data[start:pos])
        self._string_cache[idx] = value
        return value

    def string_blob_size(self, idx: int) -> int:
        size = self._string_blob_size.get(idx)
        if size is None:
            self.string(idx)
            size = self._string_blob_size.get(idx, 0)
        return size

    def type_descriptor(self, type_idx: int) -> str:
        if type_idx < 0 or type_idx >= self.type_ids_size:
            raise DexError(f"type index {type_idx} out of range")
        descriptor_idx = _u4(self.data, self.type_ids_off + 4 * type_idx)
        return self.string(descriptor_idx)

    def type_string_idx(self, type_idx: int) -> int | None:
        if type_idx < 0 or type_idx >= self.type_ids_size:
            return None
        return _u4(self.data, self.type_ids_off + 4 * type_idx)

    def field_name_idx(self, field_idx: int) -> int | None:
        if field_idx < 0 or field_idx >= self.field_ids_size:
            return None
        return _u4(self.data, self.field_ids_off + 8 * field_idx + 4)

    def field_type_idx(self, field_idx: int) -> int | None:
        if field_idx < 0 or field_idx >= self.field_ids_size:
            return None
        # field_id_item: class_idx(u2) type_idx(u2) name_idx(u4)
        return _u2(self.data, self.field_ids_off + 8 * field_idx + 2)

    def method_name_idx(self, method_idx: int) -> int | None:
        if method_idx < 0 or method_idx >= self.method_ids_size:
            return None
        return _u4(self.data, self.method_ids_off + 8 * method_idx + 4)

    def method_proto_idx(self, method_idx: int) -> int | None:
        if method_idx < 0 or method_idx >= self.method_ids_size:
            return None
        # method_id_item: class_idx(u2) proto_idx(u2) name_idx(u4)
        return _u2(self.data, self.method_ids_off + 8 * method_idx + 2)

    def proto_string_indices(self, proto_idx: int) -> list[int]:
        """String indices owned by a proto_id (shorty + return + param types)."""
        if proto_idx < 0 or proto_idx >= self.proto_ids_size:
            return []
        base = self.proto_ids_off + 12 * proto_idx
        out = [_u4(self.data, base)]  # shorty_idx
        out.append(self.type_string_idx(_u4(self.data, base + 4)) or -1)
        params_off = _u4(self.data, base + 8)
        if params_off:
            count = _u4(self.data, params_off)
            for i in range(min(count, 4096)):
                out.append(self.type_string_idx(_u2(self.data, params_off + 4 + 2 * i)) or -1)
        return [i for i in out if i >= 0]

    def proto_descriptor(self, proto_idx: int) -> str:
        """'(Ljava/lang/String;)I' style signature for a proto_id."""
        if proto_idx < 0 or proto_idx >= self.proto_ids_size:
            return "<?>"
        base = self.proto_ids_off + 12 * proto_idx
        try:
            return_type = self.type_descriptor(_u4(self.data, base + 4))
            params_off = _u4(self.data, base + 8)
            params: list[str] = []
            if params_off:
                count = _u4(self.data, params_off)
                for i in range(min(count, 4096)):
                    params.append(self.type_descriptor(_u2(self.data, params_off + 4 + 2 * i)))
            return "(" + "".join(params) + ")" + return_type
        except Exception:  # noqa: BLE001
            return "<?>"

    def type_list_indices(self, off: int) -> tuple[list[int], int]:
        """Return (type indices, byte size) for a type_list at ``off``."""
        if not off:
            return [], 0
        count = _u4(self.data, off)
        count = min(count, 4096)
        indices = [_u2(self.data, off + 4 + 2 * i) for i in range(count)]
        return indices, 4 + 2 * count

    # -- structural size helpers ---------------------------------------------

    def encoded_value_end(self, off: int, depth: int = 0) -> int:
        if depth > 32:
            raise DexError("encoded_value nesting too deep")
        header = _u1(self.data, off)
        value_type = header & 0x1F
        arg = header >> 5
        off += 1

        # For primitive values, value_arg encodes (payload_size - 1), so the
        # payload is (arg + 1) bytes after the 1-byte header. BOOLEAN is the
        # exception: value_arg holds the value itself and there is no payload.
        if value_type == 0x1F:  # BOOLEAN: value is in value_arg, no payload
            return off
        if value_type in _PRIMITIVE_VALUE_TYPES:
            return off + arg + 1
        if value_type in _INDEX_VALUE_TYPES:
            # Index-valued types (method-type / method-handle / string / type /
            # field / method / enum). R8/D8 encode these with a fixed width of
            # (value_arg + 1) little-endian bytes rather than uleb128; reading
            # them as uleb128 desynchronises the walker on indices >= 128.
            return off + arg + 1
        if value_type == 0x1C:  # ARRAY
            count, off = _uleb128(self.data, off)
            for _ in range(min(count, 65536)):
                off = self.encoded_value_end(off, depth + 1)
            return off
        if value_type == 0x1D:  # ANNOTATION
            _type_idx, off = _uleb128(self.data, off)
            count, off = _uleb128(self.data, off)
            for _ in range(min(count, 65536)):
                _name_idx, off = _uleb128(self.data, off)
                off = self.encoded_value_end(off, depth + 1)
            return off
        if value_type == 0x1E:  # NULL
            return off
        raise DexError(f"unknown encoded_value type 0x{value_type:x}")

    def encoded_array_end(self, off: int) -> int:
        count, off = _uleb128(self.data, off)
        for _ in range(min(count, 65536)):
            off = self.encoded_value_end(off)
        return off

    def annotation_item_end(self, off: int) -> int:
        off += 1  # visibility byte
        _type_idx, off = _uleb128(self.data, off)
        count, off = _uleb128(self.data, off)
        for _ in range(min(count, 65536)):
            _name_idx, off = _uleb128(self.data, off)
            off = self.encoded_value_end(off)
        return off

    def annotation_set_end(self, off: int) -> tuple[int, list[int]]:
        count = _u4(self.data, off)
        off += 4
        items = []
        for _ in range(min(count, 65536)):
            items.append(_u4(self.data, off))
            off += 4
        return off, items

    def annotation_directory_size(self, off: int) -> tuple[int, list[int]]:
        """Return (size, annotation_item offsets) for an annotations_directory_item."""
        class_annotations_off = _u4(self.data, off)
        fields_size = _u4(self.data, off + 4)
        methods_size = _u4(self.data, off + 8)
        params_size = _u4(self.data, off + 12)
        end = off + 16 + 8 * (fields_size + methods_size + params_size)
        set_offsets: list[int] = []
        if class_annotations_off:
            set_offsets.append(class_annotations_off)
        entry_base = off + 16
        for i in range(fields_size + methods_size + params_size):
            # Each entry is 8 bytes: (field/method/param) index + annotations
            # offset. The set offset is the second u4, not the first.
            set_offsets.append(_u4(self.data, entry_base + 8 * i + 4))
        return end - off, set_offsets

    def annotations_total_size(
        self,
        off: int,
        seen_sets: set[int] | None = None,
        seen_items: set[int] | None = None,
    ) -> tuple[int, list[int]]:
        """Total bytes of an annotation directory and everything it points to.

        ``seen_sets`` / ``seen_items`` are shared across classes so that two
        classes carrying the same annotation do not double-count its bytes.
        """
        directory_size, set_offsets = self.annotation_directory_size(off)
        total = directory_size
        annotation_offsets: list[int] = []
        seen_sets = set() if seen_sets is None else seen_sets
        seen_items = set() if seen_items is None else seen_items
        for set_off in set_offsets:
            if not set_off or set_off in seen_sets:
                continue
            seen_sets.add(set_off)
            end, items = self.annotation_set_end(set_off)
            total += end - set_off
            for item_off in items:
                if item_off not in annotation_offsets:
                    annotation_offsets.append(item_off)
        for item_off in annotation_offsets:
            if item_off in seen_items:
                continue
            seen_items.add(item_off)
            total += self.annotation_item_end(item_off) - item_off
        return total, annotation_offsets

    def debug_info_end(self, off: int) -> tuple[int, list[int]]:
        """Return (end offset, parameter name string indices)."""
        _line_start, pos = _uleb128(self.data, off)
        params, pos = _uleb128(self.data, pos)
        names: list[int] = []
        for _ in range(min(params, 4096)):
            name_idx, pos = _uleb128(self.data, pos)
            if name_idx:
                names.append(name_idx - 1)
        while True:
            opcode = _u1(self.data, pos)
            pos += 1
            if opcode == 0x00:  # END_SEQUENCE
                return pos, names
            if opcode == 0x01:  # ADVANCE_PC
                _v, pos = _uleb128(self.data, pos)
            elif opcode == 0x02:  # ADVANCE_LINE
                _v, pos = _sleb128(self.data, pos)
            elif opcode == 0x03:  # START_LOCAL
                _reg, pos = _uleb128(self.data, pos)
                name_idx, pos = _uleb128(self.data, pos)
                if name_idx:
                    names.append(name_idx - 1)
                _t, pos = _uleb128(self.data, pos)
            elif opcode == 0x04:  # START_LOCAL_EXTENDED
                _reg, pos = _uleb128(self.data, pos)
                name_idx, pos = _uleb128(self.data, pos)
                if name_idx:
                    names.append(name_idx - 1)
                _t, pos = _uleb128(self.data, pos)
                _s, pos = _uleb128(self.data, pos)
            elif opcode in (0x05, 0x06):  # END_LOCAL / RESTART_LOCAL
                _reg, pos = _uleb128(self.data, pos)
            elif opcode in (0x07, 0x08):  # PROLOGUE_END / EPILOGUE_BEGIN
                pass
            elif opcode == 0x09:  # SET_FILE has a uleb128 operand
                _v, pos = _uleb128(self.data, pos)
            # 0x0a..0xff are SPECIAL opcodes: the pc/line delta is encoded in
            # the opcode byte itself, so they have NO operand. Consuming one
            # here misaligns the stream and reads garbage as local names.

    def code_item_size(self, off: int) -> tuple[int, int | None, int]:
        """Return (total bytes, debug info offset, instruction count) for a code_item.

        A code_item starts with a 16-byte header (registers, try/catch count, debug
        offset, instruction count), followed by instructions and, when present, the
        try/catch handler table.
        """
        # code_item: registers(u2) ins(u2) outs(u2) tries(u2) debug(u4) insns_size(u4)
        tries_size = _u2(self.data, off + 6)
        debug_off = _u4(self.data, off + 8)
        insns_size = _u4(self.data, off + 12)
        size = 16 + 2 * insns_size
        pos = off + size
        if tries_size:
            if insns_size & 1:  # try_item starts on a 4-byte boundary
                pos += 2
            pos += 8 * tries_size
            handlers_size, pos = _uleb128(self.data, pos)
            for _ in range(min(handlers_size, 65536)):
                handled, pos = _uleb128(self.data, pos)
                for _ in range(min(handled, 65536)):
                    _type_idx, pos = _uleb128(self.data, pos)
                    _addr, pos = _uleb128(self.data, pos)
                # catch_all_addr exists only for a zero-length handler
                if handled == 0:
                    _catch_all, pos = _uleb128(self.data, pos)
        return pos - off, debug_off or None, insns_size

    def class_data_info(
        self, off: int
    ) -> tuple[int, list[tuple[int, int]], list[tuple[int, int, int]]]:
        """Return (byte size, [(field idx, flags)], [(method idx, flags, code_off)])."""
        if not off:
            return 0, [], []
        static_fields, pos = _uleb128(self.data, off)
        instance_fields, pos = _uleb128(self.data, pos)
        direct_methods, pos = _uleb128(self.data, pos)
        virtual_methods, pos = _uleb128(self.data, pos)

        fields: list[tuple[int, int]] = []
        methods: list[tuple[int, int, int]] = []

        # Each of the four lists encodes its first index as a full value and
        # the remaining ones as deltas. The delta sequence RESTARTS per list.
        idx = 0
        for _ in range(static_fields):
            diff, pos = _uleb128(self.data, pos)
            flags, pos = _uleb128(self.data, pos)
            idx += diff
            fields.append((idx, flags))

        idx = 0
        for _ in range(instance_fields):
            diff, pos = _uleb128(self.data, pos)
            flags, pos = _uleb128(self.data, pos)
            idx += diff
            fields.append((idx, flags))

        idx = 0
        for _ in range(direct_methods):
            diff, pos = _uleb128(self.data, pos)
            flags, pos = _uleb128(self.data, pos)
            code_off, pos = _uleb128(self.data, pos)
            idx += diff
            methods.append((idx, flags, code_off))

        idx = 0
        for _ in range(virtual_methods):
            diff, pos = _uleb128(self.data, pos)
            flags, pos = _uleb128(self.data, pos)
            code_off, pos = _uleb128(self.data, pos)
            idx += diff
            methods.append((idx, flags, code_off))
        return pos - off, fields, methods

    # -- main analysis --------------------------------------------------------

    def analyze(self) -> DexAnalysis:
        result = DexAnalysis(path=self.dex_name, file_size=len(self.data))

        # Pre-compute string blob sizes (also fills the cache lazily via string()).
        for i in range(self.string_ids_size):
            try:
                self.string(i)
            except Exception as exc:  # noqa: BLE001 - keep going on malformed entries
                self._warnings.append(f"string[{i}]: {exc}")

        # ===== Pass 1: collect raw information for every class =====
        # Walk class_defs (the dex class list) and read class identity, superclass,
        # interfaces, fields, methods, annotations, static values, etc. Also:
        #   (a) add class-owned bytes to breakdown;
        #   (b) build semantic parts for the change fingerprint.
        records: list[dict] = []
        seen_annotation_sets: set[int] = set()
        seen_annotation_items: set[int] = set()
        for i in range(self.class_defs_size):
            base = self.class_defs_off + 32 * i
            try:
                class_idx = _u4(self.data, base)
                access_flags = _u4(self.data, base + 4)
                superclass_idx = _u4(self.data, base + 8)
                interfaces_off = _u4(self.data, base + 12)
                source_file_idx = _u4(self.data, base + 16)
                annotations_off = _u4(self.data, base + 20)
                class_data_off = _u4(self.data, base + 24)
                static_values_off = _u4(self.data, base + 28)
                desc = self.type_descriptor(class_idx)
            except Exception as exc:  # noqa: BLE001
                self._warnings.append(f"class_def[{i}]: {exc}")
                continue

            class_string_idx = self.type_string_idx(class_idx)
            record: dict = {
                "descriptor": desc,
                "class_idx": class_idx,
                "superclass_idx": superclass_idx,
                "interfaces_off": interfaces_off,
                "source_file_idx": source_file_idx,
                "annotations_off": annotations_off,
                "class_data_off": class_data_off,
                "static_values_off": static_values_off,
                "access_flags": access_flags,
                "strings": {class_string_idx} if class_string_idx is not None else set(),
                "types": {class_idx},
                "fields": set(),
                "methods": set(),
                "protos": set(),
                "breakdown": SizeBreakdown(def_item=32),
                "partial": False,
                "warning": "",
                "method_count": 0,
                "field_count": 0,
                # Human-readable, index-independent fingerprint parts. Raw DEX
                # indices shift whenever a class is added/removed, so hashing
                # raw bytes would mark nearly every class as "modified".
                "semantic": [f"C:{access_flags}:{desc}"],
            }

            superclass_string_idx = self.type_string_idx(superclass_idx)
            if superclass_string_idx is not None:
                record["types"].add(superclass_idx)
                record["strings"].add(superclass_string_idx)
                try:
                    record["semantic"].append("S:" + self.type_descriptor(superclass_idx))
                except Exception:  # noqa: BLE001
                    pass

            if interfaces_off:
                try:
                    indices, size = self.type_list_indices(interfaces_off)
                    record["breakdown"].type_lists += size
                    try:
                        record["semantic"].append(
                            "I:" + ",".join(sorted(self.type_descriptor(t) for t in indices))
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    for t in indices:
                        record["types"].add(t)
                        s = self.type_string_idx(t)
                        if s is not None:
                            record["strings"].add(s)
                except Exception as exc:  # noqa: BLE001
                    record["partial"] = True
                    record["warning"] = f"interfaces: {exc}"

            if source_file_idx < self.string_ids_size:
                record["strings"].add(source_file_idx)
                try:
                    record["semantic"].append("SF:" + self.string(source_file_idx))
                except Exception:  # noqa: BLE001
                    pass

            # class_data
            if class_data_off:
                try:
                    cd_size, fields, methods = self.class_data_info(class_data_off)
                    record["breakdown"].class_data += cd_size
                    record["field_count"] = len(fields)
                    record["method_count"] = len(methods)
                    for f, flags in fields:
                        record["fields"].add(f)
                        n = self.field_name_idx(f)
                        name = self.string(n) if n is not None else "?"
                        t = self.field_type_idx(f)
                        type_desc = self.type_descriptor(t) if t is not None else "?"
                        record["semantic"].append(f"F:{flags}:{name}:{type_desc}")
                        if n is not None:
                            record["strings"].add(n)
                        if t is not None:
                            record["types"].add(t)
                            s = self.type_string_idx(t)
                            if s is not None:
                                record["strings"].add(s)
                    for m, flags, code_off in methods:
                        record["methods"].add(m)
                        n = self.method_name_idx(m)
                        name = self.string(n) if n is not None else "?"
                        if n is not None:
                            record["strings"].add(n)
                        p = self.method_proto_idx(m)
                        proto = self.proto_descriptor(p) if p is not None else "?"
                        spec = f"M:{flags}:{name}:{proto}"
                        if p is not None:
                            record["protos"].add(p)
                            for s in self.proto_string_indices(p):
                                record["strings"].add(s)
                        if code_off:
                            code_size, debug_off, insns = self.code_item_size(code_off)
                            record["breakdown"].code += code_size
                            # insns_size (instruction count) is stable; the raw
                            # byte size includes ULEB128 exception-handler
                            # indices which shift when other classes change.
                            spec += f":ins={insns}"
                            if debug_off:
                                try:
                                    d_end, names = self.debug_info_end(debug_off)
                                    record["breakdown"].debug_info += d_end - debug_off
                                    name_values = []
                                    for idx in names:
                                        if idx < self.string_ids_size:
                                            record["strings"].add(idx)
                                            name_values.append(self.string(idx))
                                    spec += ":dbg=" + ",".join(sorted(name_values))
                                except Exception as exc:  # noqa: BLE001
                                    record["partial"] = True
                                    record["warning"] = f"debug_info: {exc}"
                        record["semantic"].append(spec)
                except Exception as exc:  # noqa: BLE001
                    record["partial"] = True
                    record["warning"] = f"class_data: {exc}"

            # annotations -> also pull type indices out of the encoded values
            if annotations_off:
                try:
                    ann_size, ann_offsets = self.annotations_total_size(
                        annotations_off, seen_annotation_sets, seen_annotation_items
                    )
                    record["breakdown"].annotations += ann_size
                    for item_off in ann_offsets:
                        try:
                            self.annotation_item_end(item_off)
                            # Collect type_idx referenced at the head of every
                            # annotation_item and every encoded ANNOTATION value.
                            pos = item_off + 1
                            t, pos = _uleb128(self.data, pos)
                            record["types"].add(t)
                            s = self.type_string_idx(t)
                            if s is not None:
                                record["strings"].add(s)
                            try:
                                record["semantic"].append("A:" + self.type_descriptor(t))
                            except Exception:  # noqa: BLE001
                                pass
                            count, pos = _uleb128(self.data, pos)
                            for _ in range(min(count, 4096)):
                                _name_idx, pos = _uleb128(self.data, pos)
                                pos = self._collect_value_types(pos, record, depth=0)
                        except Exception:  # noqa: BLE001
                            pass
                except Exception as exc:  # noqa: BLE001
                    record["partial"] = True
                    record["warning"] = (record["warning"] + f"; annotations: {exc}").strip("; ")

            # static values
            if static_values_off:
                try:
                    end = self.encoded_array_end(static_values_off)
                    record["breakdown"].static_values += end - static_values_off
                    pos = static_values_off
                    count, pos = _uleb128(self.data, pos)
                    for _ in range(min(count, 4096)):
                        pos = self._collect_value_types(pos, record, depth=0)
                except Exception:  # noqa: BLE001
                    pass

            # remove invalid indices
            record["strings"] = {s for s in record["strings"] if 0 <= s < self.string_ids_size}
            record["types"] = {t for t in record["types"] if 0 <= t < self.type_ids_size}
            record["fields"] = {f for f in record["fields"] if 0 <= f < self.field_ids_size}
            record["methods"] = {m for m in record["methods"] if 0 <= m < self.method_ids_size}
            record["protos"] = {p for p in record["protos"] if 0 <= p < self.proto_ids_size}
            records.append(record)

        # ===== Pass 2: distribute shared tables and strings to classes =====
        # Pass 1 recorded which type/field/method/string entries each class refers to.
        # Those tables are global; charging them per class would double-count.
        # Sort classes by name (fixed order = deterministic result), then let
        # the first referencing class own each shared entry (setdefault).
        records.sort(key=lambda r: r["descriptor"])

        owner_type: dict[int, int] = {}
        owner_field: dict[int, int] = {}
        owner_method: dict[int, int] = {}
        owner_proto: dict[int, int] = {}
        owner_string: dict[int, int] = {}

        for pos_idx, rec in enumerate(records):
            for t in rec["types"]:
                owner_type.setdefault(t, pos_idx)
            for f in rec["fields"]:
                owner_field.setdefault(f, pos_idx)
            for m in rec["methods"]:
                owner_method.setdefault(m, pos_idx)
            for p in rec["protos"]:
                owner_proto.setdefault(p, pos_idx)
            for s in rec["strings"]:
                owner_string.setdefault(s, pos_idx)

        type_counts = Counter(owner_type.values())
        field_counts = Counter(owner_field.values())
        method_counts = Counter(owner_method.values())
        proto_counts = Counter(owner_proto.values())
        string_counts = Counter(owner_string.values())
        strings_by_owner: dict[int, list[int]] = {}
        for string_idx, pos_idx in owner_string.items():
            strings_by_owner.setdefault(pos_idx, []).append(string_idx)

        for pos_idx, rec in enumerate(records):
            rec["breakdown"].identifiers += (
                4 * type_counts[pos_idx]
                + 8 * field_counts[pos_idx]
                + 8 * method_counts[pos_idx]
                + 12 * proto_counts[pos_idx]
                + 4 * string_counts[pos_idx]
            )
            for s in strings_by_owner.get(pos_idx, []):
                rec["breakdown"].strings += self.string_blob_size(s)

            # ===== Semantic fingerprint: did this class really change? =====
            # Only source-meaningful data enters the fingerprint: field names, method
            # signatures, local variable names, annotations. Never raw dex bytes/indices.
            # Adding/removing other classes renumbers every index, so raw bytes change
            # even when this class's source did not; comparing them would flood the report.
            digest = hashlib.sha256()
            # NOTE: do NOT hash rec["strings"] here. That set is the result of
            # first-owner attribution and shifts when unrelated classes change;
            # hashing it re-introduces the false "modified" noise we are
            # avoiding. All names that truly belong to the class are already
            # in rec["semantic"] (superclass, interfaces, fields, methods,
            # debug local names, annotations, source file).
            for part in sorted(rec["semantic"]):
                digest.update(part.encode("utf-8", "replace"))
                digest.update(b"\x00")

            result.classes.append(
                DexClass(
                    name=rec["descriptor"],
                    dex_name=self.dex_name,
                    size=rec["breakdown"].total,
                    breakdown=rec["breakdown"],
                    content_hash=digest.hexdigest(),
                    methods=rec["method_count"],
                    fields=rec["field_count"],
                    partial=rec["partial"],
                    warning=rec["warning"],
                    semantic_parts=sorted(rec["semantic"]),
                )
            )

        attributed = sum(c.size for c in result.classes)
        result.unattributed = max(0, len(self.data) - attributed)
        result.warnings = self._warnings
        return result

    def _collect_value_types(self, off: int, rec: dict, depth: int) -> int:
        """Walk one encoded_value, recording type indices it references."""
        if depth > 32:
            return off
        header = _u1(self.data, off)
        value_type = header & 0x1F
        arg = header >> 5
        off += 1
        if value_type == 0x1F:  # BOOLEAN: value is in value_arg, no payload
            return off
        if value_type in _PRIMITIVE_VALUE_TYPES:
            return off + arg + 1
        if value_type in _INDEX_VALUE_TYPES:
            # Fixed-width little-endian index (value_arg + 1 bytes), matching
            # how R8/D8 emit encoded_value indices. See encoded_value_end.
            width = arg + 1
            val = int.from_bytes(self.data[off:off + width], "little")
            off += width
            if value_type == 0x18:  # TYPE
                rec["types"].add(val)
                s = self.type_string_idx(val)
                if s is not None:
                    rec["strings"].add(s)
            elif value_type == 0x1B:  # ENUM -> field
                rec["fields"].add(val)
            elif value_type == 0x17:  # STRING
                rec["strings"].add(val)
            return off
        if value_type == 0x1C:
            count, off = _uleb128(self.data, off)
            for _ in range(min(count, 4096)):
                off = self._collect_value_types(off, rec, depth + 1)
            return off
        if value_type == 0x1D:
            t, off = _uleb128(self.data, off)
            rec["types"].add(t)
            s = self.type_string_idx(t)
            if s is not None:
                rec["strings"].add(s)
            count, off = _uleb128(self.data, off)
            for _ in range(min(count, 4096)):
                name_idx, off = _uleb128(self.data, off)
                rec["strings"].add(name_idx)
                off = self._collect_value_types(off, rec, depth + 1)
            return off
        if value_type == 0x1E:
            return off
        return off
