package top.jayvin.apkdiff;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * DEX parser: attributes every byte of a dex file to a concrete class.
 *
 * <p>The goal is not full decompilation, only answering "how many bytes does this class
 * cost?". Bytes that clearly belong to a class (class_def, class_data, code, debug info,
 * annotations, static values) are charged directly. Shared tables (type / field / method /
 * proto / string pools) are charged to the first class (in descriptor order) that references
 * an entry, which keeps the result deterministic. Everything left over (header, map list,
 * unreferenced strings, padding) lands in {@code unattributed}, so that</p>
 *
 * <pre>sum(class sizes) + unattributed == dex file size</pre>
 *
 * <p>Change detection uses a semantic fingerprint (class name, superclass, interfaces, field
 * and method signatures, debug local names, annotation types, source file) rather than raw
 * dex bytes: adding or removing a class reshuffles every index pool, which would otherwise
 * mark nearly every class as modified.</p>
 */
public class DexFile {
    private final byte[] data;
    private final String dexName;

    private final int stringIdsSize;
    private final int stringIdsOff;
    private final int typeIdsSize;
    private final int typeIdsOff;
    private final int protoIdsSize;
    private final int protoIdsOff;
    private final int fieldIdsSize;
    private final int fieldIdsOff;
    private final int methodIdsSize;
    private final int methodIdsOff;
    private final int classDefsSize;
    private final int classDefsOff;

    private final HashMap<Integer, String> stringCache = new HashMap<>();
    private final HashMap<Integer, Integer> stringBlobSizes = new HashMap<>();
    private final List<String> parseWarnings = new ArrayList<>();

    public DexFile(byte[] data) {
        this(data, "classes.dex");
    }

    public DexFile(byte[] data, String dexName) {
        this.data = data;
        this.dexName = dexName;
        String magic = data.length >= 4
                ? new String(data, 0, 4, StandardCharsets.ISO_8859_1)
                : "";
        if (data.length < 112 || !"dex\n".equals(magic)) {
            throw new DexException(dexName + ": not a DEX file");
        }
        int endian = u4(data, 0x28);
        if (endian != 0x12345678) {
            throw new DexException(
                    dexName + ": unsupported endian tag 0x" + Integer.toUnsignedString(endian, 16));
        }

        stringIdsSize = u4(data, 0x38);
        stringIdsOff = u4(data, 0x3c);
        typeIdsSize = u4(data, 0x40);
        typeIdsOff = u4(data, 0x44);
        protoIdsSize = u4(data, 0x48);
        protoIdsOff = u4(data, 0x4c);
        fieldIdsSize = u4(data, 0x50);
        fieldIdsOff = u4(data, 0x54);
        methodIdsSize = u4(data, 0x58);
        methodIdsOff = u4(data, 0x5c);
        classDefsSize = u4(data, 0x60);
        classDefsOff = u4(data, 0x64);
    }

    // ------------------------------------------------------------------
    // low level readers
    // ------------------------------------------------------------------

    static int u1(byte[] data, int off) {
        if (off < 0 || off >= data.length) {
            throw new DexException("u1 read out of bounds at 0x" + Integer.toHexString(off));
        }
        return data[off] & 0xff;
    }

    static int u2(byte[] data, int off) {
        if (off < 0 || off + 2 > data.length) {
            throw new DexException("u2 read out of bounds at 0x" + Integer.toHexString(off));
        }
        return (data[off] & 0xff) | ((data[off + 1] & 0xff) << 8);
    }

    static int u4(byte[] data, int off) {
        if (off < 0 || off + 4 > data.length) {
            throw new DexException("u4 read out of bounds at 0x" + Integer.toHexString(off));
        }
        return (data[off] & 0xff)
                | ((data[off + 1] & 0xff) << 8)
                | ((data[off + 2] & 0xff) << 16)
                | ((data[off + 3] & 0xff) << 24);
    }

    /** Read an unsigned LEB128 value; returns {value, new offset}. */
    static int[] uleb128(byte[] data, int off) {
        int result = 0;
        int shift = 0;
        int pos = off;
        while (true) {
            int b = u1(data, pos);
            pos++;
            result |= (b & 0x7f) << shift;
            if ((b & 0x80) == 0) {
                return new int[]{result, pos};
            }
            shift += 7;
            if (shift > 35) {
                throw new DexException("uleb128 too long");
            }
        }
    }

    /** Read a signed LEB128 value; returns {value, new offset}. */
    static int[] sleb128(byte[] data, int off) {
        int result = 0;
        int shift = 0;
        int pos = off;
        while (true) {
            int b = u1(data, pos);
            pos++;
            result |= (b & 0x7f) << shift;
            shift += 7;
            if ((b & 0x80) == 0) {
                if ((b & 0x40) != 0) {
                    result -= 1 << shift;
                }
                return new int[]{result, pos};
            }
            if (shift > 63) {
                throw new DexException("sleb128 too long");
            }
        }
    }

    /**
     * Decode DEX MUTF-8, folding surrogate pairs back into codepoints.
     *
     * <p>MUTF-8 encodes NUL as 0xC0 0x80 and keeps surrogate halves separate; this normalises
     * the result to standard Java strings.</p>
     */
    static String decodeMutf8(byte[] raw) {
        return decodeMutf8(raw, 0, raw.length);
    }

    static String decodeMutf8(byte[] data, int start, int end) {
        int[] units = new int[Math.max(0, end - start)];
        int count = 0;
        int i = start;
        while (i < end) {
            int b = data[i] & 0xff;
            if (b == 0) {
                break;
            }
            if (b < 0x80) {
                units[count++] = b;
                i += 1;
            } else if ((b & 0xE0) == 0xC0) {
                if (i + 1 >= end) {
                    break;
                }
                units[count++] = ((b & 0x1f) << 6) | ((data[i + 1] & 0xff) & 0x3f);
                i += 2;
            } else if ((b & 0xF0) == 0xE0) {
                if (i + 2 >= end) {
                    break;
                }
                units[count++] = ((b & 0x0f) << 12)
                        | (((data[i + 1] & 0xff) & 0x3f) << 6)
                        | ((data[i + 2] & 0xff) & 0x3f);
                i += 3;
            } else {
                units[count++] = 0xFFFD;
                i += 1;
            }
        }

        StringBuilder out = new StringBuilder(count);
        int j = 0;
        while (j < count) {
            int u = units[j];
            if (u >= 0xD800 && u <= 0xDBFF
                    && j + 1 < count
                    && units[j + 1] >= 0xDC00 && units[j + 1] <= 0xDFFF) {
                int low = units[j + 1];
                int cp = 0x10000 + ((u - 0xD800) << 10) + (low - 0xDC00);
                out.appendCodePoint(cp);
                j += 2;
            } else {
                out.append((char) (u <= 0x10FFFF ? u : 0xFFFD));
                j += 1;
            }
        }
        return out.toString();
    }

    /** 'Lcom/foo/Bar;' to 'com.foo.Bar'; '$' is kept for inner classes. */
    public static String descriptorToClassName(String desc) {
        if (desc.startsWith("L") && desc.endsWith(";")) {
            return desc.substring(1, desc.length() - 1).replace('/', '.');
        }
        return desc;
    }

    // ------------------------------------------------------------------
    // string / type helpers
    // ------------------------------------------------------------------

    public String string(int idx) {
        String cached = stringCache.get(idx);
        if (cached != null) {
            return cached;
        }
        if (idx < 0 || idx >= stringIdsSize) {
            throw new DexException("string index " + idx + " out of range");
        }
        int off = u4(data, stringIdsOff + 4 * idx);
        int[] valueStart = uleb128(data, off);
        int pos = valueStart[1];
        while (u1(data, pos) != 0) {
            pos++;
        }
        stringBlobSizes.put(idx, pos + 1 - off);
        String value = decodeMutf8(data, valueStart[1], pos);
        stringCache.put(idx, value);
        return value;
    }

    public int stringBlobSize(int idx) {
        Integer size = stringBlobSizes.get(idx);
        if (size == null) {
            string(idx);
            size = stringBlobSizes.get(idx);
        }
        return size == null ? 0 : size;
    }

    public String typeDescriptor(int typeIdx) {
        if (typeIdx < 0 || typeIdx >= typeIdsSize) {
            throw new DexException("type index " + typeIdx + " out of range");
        }
        return string(u4(data, typeIdsOff + 4 * typeIdx));
    }

    public Integer typeStringIdx(int typeIdx) {
        if (typeIdx < 0 || typeIdx >= typeIdsSize) {
            return null;
        }
        return u4(data, typeIdsOff + 4 * typeIdx);
    }

    public Integer fieldNameIdx(int fieldIdx) {
        if (fieldIdx < 0 || fieldIdx >= fieldIdsSize) {
            return null;
        }
        return u4(data, fieldIdsOff + 8 * fieldIdx + 4);
    }

    public Integer fieldTypeIdx(int fieldIdx) {
        if (fieldIdx < 0 || fieldIdx >= fieldIdsSize) {
            return null;
        }
        // field_id_item: class_idx(u2) type_idx(u2) name_idx(u4)
        return u2(data, fieldIdsOff + 8 * fieldIdx + 2);
    }

    public Integer methodNameIdx(int methodIdx) {
        if (methodIdx < 0 || methodIdx >= methodIdsSize) {
            return null;
        }
        return u4(data, methodIdsOff + 8 * methodIdx + 4);
    }

    public Integer methodProtoIdx(int methodIdx) {
        if (methodIdx < 0 || methodIdx >= methodIdsSize) {
            return null;
        }
        // method_id_item: class_idx(u2) proto_idx(u2) name_idx(u4)
        return u2(data, methodIdsOff + 8 * methodIdx + 2);
    }

    /** String indices owned by a proto_id (shorty + return + param types). */
    public List<Integer> protoStringIndices(int protoIdx) {
        if (protoIdx < 0 || protoIdx >= protoIdsSize) {
            return Collections.emptyList();
        }
        int base = protoIdsOff + 12 * protoIdx;
        ArrayList<Integer> out = new ArrayList<>();
        out.add(u4(data, base)); // shorty_idx
        // The Python implementation used `type_string_idx(...) or -1`, which drops a valid
        // index of 0. Keep that exact behaviour so byte attribution matches upstream.
        Integer returnType = typeStringIdx(u4(data, base + 4));
        if (returnType != null && returnType != 0) {
            out.add(returnType);
        }
        int paramsOff = u4(data, base + 8);
        if (paramsOff != 0) {
            int count = Math.min(u4(data, paramsOff), 4096);
            for (int i = 0; i < count; i++) {
                Integer param = typeStringIdx(u2(data, paramsOff + 4 + 2 * i));
                if (param != null && param != 0) {
                    out.add(param);
                }
            }
        }
        return out;
    }

    /** '(Ljava/lang/String;)I' style signature for a proto_id. */
    public String protoDescriptor(int protoIdx) {
        if (protoIdx < 0 || protoIdx >= protoIdsSize) {
            return "<?>";
        }
        int base = protoIdsOff + 12 * protoIdx;
        try {
            String returnType = typeDescriptor(u4(data, base + 4));
            int paramsOff = u4(data, base + 8);
            StringBuilder params = new StringBuilder();
            if (paramsOff != 0) {
                int count = Math.min(u4(data, paramsOff), 4096);
                for (int i = 0; i < count; i++) {
                    params.append(typeDescriptor(u2(data, paramsOff + 4 + 2 * i)));
                }
            }
            return "(" + params + ")" + returnType;
        } catch (RuntimeException exc) {
            return "<?>";
        }
    }

    /** Type indices and byte size for a type_list at {@code off}. */
    TypeList typeListIndices(int off) {
        if (off == 0) {
            return new TypeList(new int[0], 0);
        }
        int count = Math.min(u4(data, off), 4096);
        int[] indices = new int[count];
        for (int i = 0; i < count; i++) {
            indices[i] = u2(data, off + 4 + 2 * i);
        }
        return new TypeList(indices, 4 + 2 * count);
    }

    // ------------------------------------------------------------------
    // structural size helpers
    // ------------------------------------------------------------------

    int encodedValueEnd(int off, int depth) {
        if (depth > 32) {
            throw new DexException("encoded_value nesting too deep");
        }
        int header = u1(data, off);
        int valueType = header & 0x1f;
        int arg = header >>> 5;
        int pos = off + 1;

        // For primitive values, value_arg encodes (payload_size - 1), so the payload is
        // (arg + 1) bytes after the 1-byte header. BOOLEAN is the exception: value_arg holds
        // the value itself and there is no payload.
        if (valueType == 0x1f) {
            return pos;
        }
        if (isPrimitiveValue(valueType)) {
            return pos + arg + 1;
        }
        if (valueType >= 0x15 && valueType <= 0x1b) {
            // Index-valued types (method-type / method-handle / string / type / field /
            // method / enum). R8/D8 encode these with a fixed width of (value_arg + 1)
            // little-endian bytes rather than uleb128; reading them as uleb128
            // desynchronises the walker on indices >= 128.
            return pos + arg + 1;
        }
        if (valueType == 0x1c) { // ARRAY
            int[] count = uleb128(data, pos);
            pos = count[1];
            for (int i = 0; i < Math.min(count[0], 65536); i++) {
                pos = encodedValueEnd(pos, depth + 1);
            }
            return pos;
        }
        if (valueType == 0x1d) { // ANNOTATION
            int[] type = uleb128(data, pos);
            pos = type[1];
            int[] count = uleb128(data, pos);
            pos = count[1];
            for (int i = 0; i < Math.min(count[0], 65536); i++) {
                int[] name = uleb128(data, pos);
                pos = name[1];
                pos = encodedValueEnd(pos, depth + 1);
            }
            return pos;
        }
        if (valueType == 0x1e) { // NULL
            return pos;
        }
        throw new DexException("unknown encoded_value type 0x" + Integer.toHexString(valueType));
    }

    private static boolean isPrimitiveValue(int valueType) {
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

    int encodedArrayEnd(int off) {
        int[] count = uleb128(data, off);
        int pos = count[1];
        for (int i = 0; i < Math.min(count[0], 65536); i++) {
            pos = encodedValueEnd(pos, 0);
        }
        return pos;
    }

    int annotationItemEnd(int off) {
        int pos = off + 1; // visibility byte
        int[] type = uleb128(data, pos);
        pos = type[1];
        int[] count = uleb128(data, pos);
        pos = count[1];
        for (int i = 0; i < Math.min(count[0], 65536); i++) {
            int[] name = uleb128(data, pos);
            pos = name[1];
            pos = encodedValueEnd(pos, 0);
        }
        return pos;
    }

    AnnotationSet annotationSetEnd(int off) {
        int count = u4(data, off);
        int pos = off + 4;
        ArrayList<Integer> items = new ArrayList<>();
        for (int i = 0; i < Math.min(count, 65536); i++) {
            items.add(u4(data, pos));
            pos += 4;
        }
        return new AnnotationSet(pos, items);
    }

    /** Size and annotation_item offsets for an annotations_directory_item. */
    AnnotationDirectory annotationDirectorySize(int off) {
        int classAnnotationsOff = u4(data, off);
        int fieldsSize = u4(data, off + 4);
        int methodsSize = u4(data, off + 8);
        int paramsSize = u4(data, off + 12);
        int end = off + 16 + 8 * (fieldsSize + methodsSize + paramsSize);
        ArrayList<Integer> setOffsets = new ArrayList<>();
        if (classAnnotationsOff != 0) {
            setOffsets.add(classAnnotationsOff);
        }
        int entryBase = off + 16;
        for (int i = 0; i < fieldsSize + methodsSize + paramsSize; i++) {
            // Each entry is 8 bytes: (field/method/param) index + annotations offset.
            // The set offset is the second u4, not the first.
            setOffsets.add(u4(data, entryBase + 8 * i + 4));
        }
        return new AnnotationDirectory(end - off, setOffsets);
    }

    /**
     * Total bytes of an annotation directory and everything it points to.
     *
     * <p>{@code seenSets} / {@code seenItems} are shared across classes so that two classes
     * carrying the same annotation do not double-count its bytes.</p>
     */
    AnnotationTotal annotationsTotalSize(int off, Set<Integer> seenSets, Set<Integer> seenItems) {
        AnnotationDirectory directory = annotationDirectorySize(off);
        int total = directory.size;
        ArrayList<Integer> annotationOffsets = new ArrayList<>();
        Set<Integer> localOffsets = new HashSet<>();
        for (Integer setOff : directory.setOffsets) {
            if (setOff == 0 || seenSets.contains(setOff)) {
                continue;
            }
            seenSets.add(setOff);
            AnnotationSet set = annotationSetEnd(setOff);
            total += set.end - setOff;
            for (Integer itemOff : set.items) {
                if (localOffsets.add(itemOff)) {
                    annotationOffsets.add(itemOff);
                }
            }
        }
        for (Integer itemOff : annotationOffsets) {
            if (seenItems.contains(itemOff)) {
                continue;
            }
            seenItems.add(itemOff);
            total += annotationItemEnd(itemOff) - itemOff;
        }
        return new AnnotationTotal(total, annotationOffsets);
    }

    /** End offset and parameter/local name string indices. */
    DebugInfo debugInfoEnd(int off) {
        int[] lineStart = uleb128(data, off);
        int pos = lineStart[1];
        int[] params = uleb128(data, pos);
        pos = params[1];
        ArrayList<Integer> names = new ArrayList<>();
        for (int i = 0; i < Math.min(params[0], 4096); i++) {
            int[] nameIdx = uleb128(data, pos);
            pos = nameIdx[1];
            if (nameIdx[0] != 0) {
                names.add(nameIdx[0] - 1);
            }
        }
        while (true) {
            int opcode = u1(data, pos);
            pos++;
            switch (opcode) {
                case 0x00: // END_SEQUENCE
                    return new DebugInfo(pos, names);
                case 0x01: // ADVANCE_PC
                    pos = uleb128(data, pos)[1];
                    break;
                case 0x02: // ADVANCE_LINE
                    pos = sleb128(data, pos)[1];
                    break;
                case 0x03: { // START_LOCAL
                    pos = uleb128(data, pos)[1];
                    int[] nameIdx = uleb128(data, pos);
                    pos = nameIdx[1];
                    if (nameIdx[0] != 0) {
                        names.add(nameIdx[0] - 1);
                    }
                    pos = uleb128(data, pos)[1];
                    break;
                }
                case 0x04: { // START_LOCAL_EXTENDED
                    pos = uleb128(data, pos)[1];
                    int[] nameIdx = uleb128(data, pos);
                    pos = nameIdx[1];
                    if (nameIdx[0] != 0) {
                        names.add(nameIdx[0] - 1);
                    }
                    pos = uleb128(data, pos)[1];
                    pos = uleb128(data, pos)[1];
                    break;
                }
                case 0x05: // END_LOCAL
                case 0x06: // RESTART_LOCAL
                    pos = uleb128(data, pos)[1];
                    break;
                case 0x07: // PROLOGUE_END
                case 0x08: // EPILOGUE_BEGIN
                    break;
                case 0x09: // SET_FILE
                    pos = uleb128(data, pos)[1];
                    break;
                default:
                    // 0x0a..0xff are SPECIAL opcodes: the pc/line delta is encoded in the
                    // opcode byte itself, so they have NO operand. Consuming one here
                    // misaligns the stream and reads garbage as local names.
                    break;
            }
        }
    }

    /** Size of a method's code_item: total bytes, debug info offset (0 = none), insns count. */
    CodeItem codeItemSize(int off) {
        // code_item: registers(u2) ins(u2) outs(u2) tries(u2) debug(u4) insns_size(u4)
        int triesSize = u2(data, off + 6);
        int debugOff = u4(data, off + 8);
        int insnsSize = u4(data, off + 12);
        int pos = off + 16 + 2 * insnsSize;
        if (triesSize != 0) {
            if ((insnsSize & 1) != 0) {
                pos += 2; // try_item starts on a 4-byte boundary
            }
            pos += 8 * triesSize;
            int[] handlersSize = uleb128(data, pos);
            pos = handlersSize[1];
            for (int i = 0; i < Math.min(handlersSize[0], 65536); i++) {
                int[] handled = uleb128(data, pos);
                pos = handled[1];
                for (int j = 0; j < Math.min(handled[0], 65536); j++) {
                    pos = uleb128(data, pos)[1];
                    pos = uleb128(data, pos)[1];
                }
                // catch_all_addr exists only for a zero-length handler
                if (handled[0] == 0) {
                    pos = uleb128(data, pos)[1];
                }
            }
        }
        return new CodeItem(pos - off, debugOff, insnsSize);
    }

    /** Byte size, fields (idx, flags), and methods (idx, flags, code_off). */
    ClassData classDataInfo(int off) {
        if (off == 0) {
            return new ClassData(0, Collections.emptyList(), Collections.emptyList());
        }
        int[] staticFields = uleb128(data, off);
        int pos = staticFields[1];
        int[] instanceFields = uleb128(data, pos);
        pos = instanceFields[1];
        int[] directMethods = uleb128(data, pos);
        pos = directMethods[1];
        int[] virtualMethods = uleb128(data, pos);
        pos = virtualMethods[1];

        ArrayList<int[]> fields = new ArrayList<>();
        ArrayList<int[]> methods = new ArrayList<>();

        // Each of the four lists encodes its first index as a full value and the remaining
        // ones as deltas. The delta sequence RESTARTS per list.
        pos = readFields(data, pos, staticFields[0], fields);
        pos = readFields(data, pos, instanceFields[0], fields);
        pos = readMethods(data, pos, directMethods[0], methods);
        pos = readMethods(data, pos, virtualMethods[0], methods);
        return new ClassData(pos - off, fields, methods);
    }

    private int readFields(byte[] data, int pos, int count, List<int[]> fields) {
        int idx = 0;
        for (int i = 0; i < count; i++) {
            int[] diff = uleb128(data, pos);
            pos = diff[1];
            int[] flags = uleb128(data, pos);
            pos = flags[1];
            idx += diff[0];
            fields.add(new int[]{idx, flags[0]});
        }
        return pos;
    }

    private int readMethods(byte[] data, int pos, int count, List<int[]> methods) {
        int idx = 0;
        for (int i = 0; i < count; i++) {
            int[] diff = uleb128(data, pos);
            pos = diff[1];
            int[] flags = uleb128(data, pos);
            pos = flags[1];
            int[] codeOff = uleb128(data, pos);
            pos = codeOff[1];
            idx += diff[0];
            methods.add(new int[]{idx, flags[0], codeOff[0]});
        }
        return pos;
    }

    // ------------------------------------------------------------------
    // main analysis
    // ------------------------------------------------------------------

    public DexAnalysis analyze() {
        DexAnalysis result = new DexAnalysis(dexName, data.length);

        // Pre-compute string blob sizes (also fills the cache lazily via string()).
        for (int i = 0; i < stringIdsSize; i++) {
            try {
                string(i);
            } catch (RuntimeException exc) {
                parseWarnings.add("string[" + i + "]: " + exc.getMessage());
            }
        }

        // === Pass 1: collect raw per-class information ===
        ArrayList<ClassRecord> records = new ArrayList<>(classDefsSize);
        Set<Integer> seenAnnotationSets = new HashSet<>();
        Set<Integer> seenAnnotationItems = new HashSet<>();
        for (int i = 0; i < classDefsSize; i++) {
            int base = classDefsOff + 32 * i;
            int classIdx = 0;
            int accessFlags = 0;
            int superclassIdx = 0;
            int interfacesOff = 0;
            int sourceFileIdx = 0;
            int annotationsOff = 0;
            int classDataOff = 0;
            int staticValuesOff = 0;
            String desc = "";
            try {
                classIdx = u4(data, base);
                accessFlags = u4(data, base + 4);
                superclassIdx = u4(data, base + 8);
                interfacesOff = u4(data, base + 12);
                sourceFileIdx = u4(data, base + 16);
                annotationsOff = u4(data, base + 20);
                classDataOff = u4(data, base + 24);
                staticValuesOff = u4(data, base + 28);
                desc = typeDescriptor(classIdx);
            } catch (RuntimeException exc) {
                parseWarnings.add("class_def[" + i + "]: " + exc.getMessage());
                continue;
            }

            ClassRecord record = new ClassRecord(desc);
            record.types.add(classIdx);
            Integer classStringIdx = typeStringIdx(classIdx);
            if (classStringIdx != null) {
                record.strings.add(classStringIdx);
            }

            // Human-readable, index-independent fingerprint parts. Raw DEX indices shift
            // whenever a class is added/removed, so hashing raw bytes would mark nearly
            // every class as "modified".
            record.semantic.add("C:" + Integer.toUnsignedString(accessFlags) + ":" + desc);

            Integer superStringIdx = typeStringIdx(superclassIdx);
            if (superStringIdx != null) {
                record.types.add(superclassIdx);
                record.strings.add(superStringIdx);
                try {
                    record.semantic.add("S:" + typeDescriptor(superclassIdx));
                } catch (RuntimeException ignored) {
                    // ignore
                }
            }

            if (interfacesOff != 0) {
                try {
                    TypeList interfaces = typeListIndices(interfacesOff);
                    record.breakdown.typeLists += interfaces.size;
                    try {
                        List<String> descriptors = new ArrayList<>();
                        for (int t : interfaces.indices) {
                            descriptors.add(typeDescriptor(t));
                        }
                        Collections.sort(descriptors);
                        record.semantic.add("I:" + String.join(",", descriptors));
                    } catch (RuntimeException ignored) {
                        // ignore
                    }
                    for (int t : interfaces.indices) {
                        record.types.add(t);
                        Integer stringIdx = typeStringIdx(t);
                        if (stringIdx != null) {
                            record.strings.add(stringIdx);
                        }
                    }
                } catch (RuntimeException exc) {
                    record.partial = true;
                    record.warning = "interfaces: " + exc.getMessage();
                }
            }

            if (sourceFileIdx < stringIdsSize) {
                record.strings.add(sourceFileIdx);
                try {
                    record.semantic.add("SF:" + string(sourceFileIdx));
                } catch (RuntimeException ignored) {
                    // ignore
                }
            }

            // class_data
            if (classDataOff != 0) {
                try {
                    ClassData cd = classDataInfo(classDataOff);
                    record.breakdown.classData += cd.size;
                    record.fieldCount = cd.fields.size();
                    record.methodCount = cd.methods.size();
                    for (int[] field : cd.fields) {
                        int f = field[0];
                        int flags = field[1];
                        record.fields.add(f);
                        Integer fieldNameIdx = fieldNameIdx(f);
                        String name = fieldNameIdx != null ? string(fieldNameIdx) : "?";
                        Integer fieldTypeIdx = fieldTypeIdx(f);
                        String typeDesc = fieldTypeIdx != null
                                ? typeDescriptor(fieldTypeIdx) : "?";
                        record.semantic.add("F:" + flags + ":" + name + ":" + typeDesc);
                        if (fieldNameIdx != null) {
                            record.strings.add(fieldNameIdx);
                        }
                        if (fieldTypeIdx != null) {
                            record.types.add(fieldTypeIdx);
                            Integer stringIdx = typeStringIdx(fieldTypeIdx);
                            if (stringIdx != null) {
                                record.strings.add(stringIdx);
                            }
                        }
                    }
                    for (int[] method : cd.methods) {
                        int m = method[0];
                        int flags = method[1];
                        int codeOff = method[2];
                        record.methods.add(m);
                        Integer methodNameIdx = methodNameIdx(m);
                        String name = methodNameIdx != null ? string(methodNameIdx) : "?";
                        if (methodNameIdx != null) {
                            record.strings.add(methodNameIdx);
                        }
                        Integer protoIdx = methodProtoIdx(m);
                        String proto = protoIdx != null ? protoDescriptor(protoIdx) : "?";
                        StringBuilder spec = new StringBuilder(
                                "M:" + flags + ":" + name + ":" + proto);
                        if (protoIdx != null) {
                            record.protos.add(protoIdx);
                            for (Integer s : protoStringIndices(protoIdx)) {
                                record.strings.add(s);
                            }
                        }
                        if (codeOff != 0) {
                            CodeItem code = codeItemSize(codeOff);
                            record.breakdown.code += code.size;
                            // insns_size (instruction count) is stable; the raw byte size
                            // includes ULEB128 exception-handler indices which shift when
                            // other classes change.
                            spec.append(":ins=").append(code.insnsSize);
                            if (code.debugOff != 0) {
                                try {
                                    DebugInfo debug = debugInfoEnd(code.debugOff);
                                    record.breakdown.debugInfo += debug.end - code.debugOff;
                                    List<String> nameValues = new ArrayList<>();
                                    for (Integer idx : debug.names) {
                                        if (idx < stringIdsSize) {
                                            record.strings.add(idx);
                                            nameValues.add(string(idx));
                                        }
                                    }
                                    Collections.sort(nameValues);
                                    spec.append(":dbg=").append(String.join(",", nameValues));
                                } catch (RuntimeException exc) {
                                    record.partial = true;
                                    record.warning = "debug_info: " + exc.getMessage();
                                }
                            }
                        }
                        record.semantic.add(spec.toString());
                    }
                } catch (RuntimeException exc) {
                    record.partial = true;
                    record.warning = "class_data: " + exc.getMessage();
                }
            }

            // annotations -> also pull type indices out of the encoded values
            if (annotationsOff != 0) {
                try {
                    AnnotationTotal annotations =
                            annotationsTotalSize(annotationsOff, seenAnnotationSets, seenAnnotationItems);
                    record.breakdown.annotations += annotations.size;
                    for (Integer itemOff : annotations.offsets) {
                        try {
                            annotationItemEnd(itemOff);
                            int pos = itemOff + 1;
                            int[] type = uleb128(data, pos);
                            pos = type[1];
                            record.types.add(type[0]);
                            Integer stringIdx = typeStringIdx(type[0]);
                            if (stringIdx != null) {
                                record.strings.add(stringIdx);
                            }
                            try {
                                record.semantic.add("A:" + typeDescriptor(type[0]));
                            } catch (RuntimeException ignored) {
                                // ignore
                            }
                            int[] count = uleb128(data, pos);
                            pos = count[1];
                            for (int ai = 0; ai < Math.min(count[0], 4096); ai++) {
                                int[] nameIdx = uleb128(data, pos);
                                pos = nameIdx[1];
                                pos = collectValueTypes(pos, record, 0);
                            }
                        } catch (RuntimeException ignored) {
                            // ignore malformed individual annotation items
                        }
                    }
                } catch (RuntimeException exc) {
                    record.partial = true;
                    record.warning = trimSemicolonSpace(
                            record.warning + "; annotations: " + exc.getMessage());
                }
            }

            // static values
            if (staticValuesOff != 0) {
                try {
                    int end = encodedArrayEnd(staticValuesOff);
                    record.breakdown.staticValues += end - staticValuesOff;
                    int pos = staticValuesOff;
                    int[] count = uleb128(data, pos);
                    pos = count[1];
                    for (int vi = 0; vi < Math.min(count[0], 4096); vi++) {
                        pos = collectValueTypes(pos, record, 0);
                    }
                } catch (RuntimeException ignored) {
                    // ignore
                }
            }

            // remove invalid indices
            record.strings.removeIf(v -> v < 0 || v >= stringIdsSize);
            record.types.removeIf(v -> v < 0 || v >= typeIdsSize);
            record.fields.removeIf(v -> v < 0 || v >= fieldIdsSize);
            record.methods.removeIf(v -> v < 0 || v >= methodIdsSize);
            record.protos.removeIf(v -> v < 0 || v >= protoIdsSize);
            records.add(record);
        }

        // === Pass 2: split shared tables / strings between classes ===
        // Each class listed what it references, but those are global shared tables. Sort
        // classes by name (deterministic order), then the first referencer of each entry
        // owns its bytes.
        records.sort(Comparator.comparing(record -> record.descriptor));

        Map<Integer, Integer> ownerType = new HashMap<>();
        Map<Integer, Integer> ownerField = new HashMap<>();
        Map<Integer, Integer> ownerMethod = new HashMap<>();
        Map<Integer, Integer> ownerProto = new HashMap<>();
        Map<Integer, Integer> ownerString = new HashMap<>();

        for (int posIdx = 0; posIdx < records.size(); posIdx++) {
            ClassRecord rec = records.get(posIdx);
            claim(ownerType, rec.types, posIdx);
            claim(ownerField, rec.fields, posIdx);
            claim(ownerMethod, rec.methods, posIdx);
            claim(ownerProto, rec.protos, posIdx);
            claim(ownerString, rec.strings, posIdx);
        }

        Map<Integer, Integer> typeCounts = countOwners(ownerType);
        Map<Integer, Integer> fieldCounts = countOwners(ownerField);
        Map<Integer, Integer> methodCounts = countOwners(ownerMethod);
        Map<Integer, Integer> protoCounts = countOwners(ownerProto);
        Map<Integer, Integer> stringCounts = countOwners(ownerString);
        Map<Integer, List<Integer>> stringsByOwner = new HashMap<>();
        for (Map.Entry<Integer, Integer> entry : ownerString.entrySet()) {
            stringsByOwner
                    .computeIfAbsent(entry.getValue(), key -> new ArrayList<>())
                    .add(entry.getKey());
        }

        for (int posIdx = 0; posIdx < records.size(); posIdx++) {
            ClassRecord rec = records.get(posIdx);
            rec.breakdown.identifiers +=
                    4L * getCount(typeCounts, posIdx)
                            + 8L * getCount(fieldCounts, posIdx)
                            + 8L * getCount(methodCounts, posIdx)
                            + 12L * getCount(protoCounts, posIdx)
                            + 4L * getCount(stringCounts, posIdx);
            for (Integer s : stringsByOwner.getOrDefault(posIdx, Collections.emptyList())) {
                rec.breakdown.strings += stringBlobSize(s);
            }

            // === Semantic fingerprint: did this class really change? ===
            // Only source-meaningful parts go into the hash. Do NOT hash rec.strings: that
            // set is the result of first-owner attribution and shifts when unrelated
            // classes change, which would re-introduce false "modified" noise.
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException exc) {
                throw new IllegalStateException("SHA-256 unavailable", exc);
            }
            List<String> semantic = new ArrayList<>(rec.semantic);
            Collections.sort(semantic);
            for (String part : semantic) {
                digest.update(part.getBytes(StandardCharsets.UTF_8));
                digest.update((byte) 0);
            }

            result.getClasses().add(new DexClass(
                    rec.descriptor,
                    dexName,
                    rec.breakdown.total(),
                    rec.breakdown,
                    Util.toHex(digest.digest()),
                    rec.methodCount,
                    rec.fieldCount,
                    rec.partial,
                    rec.warning,
                    semantic));
        }

        long attributed = 0;
        for (DexClass cls : result.getClasses()) {
            attributed += cls.getSize();
        }
        result.setUnattributed(Math.max(0L, (long) data.length - attributed));
        result.getWarnings().addAll(parseWarnings);
        return result;
    }

    private static void claim(Map<Integer, Integer> owners, Set<Integer> items, int posIdx) {
        for (Integer item : items) {
            owners.putIfAbsent(item, posIdx);
        }
    }

    private static Map<Integer, Integer> countOwners(Map<Integer, Integer> owners) {
        Map<Integer, Integer> counts = new HashMap<>();
        for (Integer owner : owners.values()) {
            counts.merge(owner, 1, Integer::sum);
        }
        return counts;
    }

    private static int getCount(Map<Integer, Integer> counts, int key) {
        Integer value = counts.get(key);
        return value == null ? 0 : value;
    }

    private static String trimSemicolonSpace(String value) {
        int start = 0;
        int end = value.length();
        while (start < end && (value.charAt(start) == ';' || value.charAt(start) == ' ')) {
            start++;
        }
        while (end > start && (value.charAt(end - 1) == ';' || value.charAt(end - 1) == ' ')) {
            end--;
        }
        return value.substring(start, end);
    }

    // collectValueTypes is called on encoded values inside annotations / static values.
    private int collectValueTypes(int off, ClassRecord rec, int depth) {
        if (depth > 32) {
            return off;
        }
        int header = u1(data, off);
        int valueType = header & 0x1f;
        int arg = header >>> 5;
        int pos = off + 1;
        if (valueType == 0x1f) {
            return pos; // BOOLEAN: value is in value_arg, no payload
        }
        if (isPrimitiveValue(valueType)) {
            return pos + arg + 1;
        }
        if (valueType >= 0x15 && valueType <= 0x1b) {
            // Fixed-width little-endian index (value_arg + 1 bytes), matching how R8/D8
            // emit encoded_value indices. See encodedValueEnd.
            int width = arg + 1;
            int value = 0;
            for (int i = 0; i < width; i++) {
                value |= (data[pos + i] & 0xff) << (8 * i);
            }
            pos += width;
            switch (valueType) {
                case 0x18: // TYPE
                    rec.types.add(value);
                    Integer stringIdx = typeStringIdx(value);
                    if (stringIdx != null) {
                        rec.strings.add(stringIdx);
                    }
                    break;
                case 0x1b: // ENUM -> field
                    rec.fields.add(value);
                    break;
                case 0x17: // STRING
                    rec.strings.add(value);
                    break;
                default:
                    break;
            }
            return pos;
        }
        if (valueType == 0x1c) {
            int[] count = uleb128(data, pos);
            pos = count[1];
            for (int i = 0; i < Math.min(count[0], 4096); i++) {
                pos = collectValueTypes(pos, rec, depth + 1);
            }
            return pos;
        }
        if (valueType == 0x1d) {
            int[] type = uleb128(data, pos);
            pos = type[1];
            rec.types.add(type[0]);
            Integer stringIdx = typeStringIdx(type[0]);
            if (stringIdx != null) {
                rec.strings.add(stringIdx);
            }
            int[] count = uleb128(data, pos);
            pos = count[1];
            for (int i = 0; i < Math.min(count[0], 4096); i++) {
                int[] nameIdx = uleb128(data, pos);
                pos = nameIdx[1];
                rec.strings.add(nameIdx[0]);
                pos = collectValueTypes(pos, rec, depth + 1);
            }
            return pos;
        }
        if (valueType == 0x1e) {
            return pos;
        }
        return pos;
    }

    // ------------------------------------------------------------------
    // small result holders
    // ------------------------------------------------------------------

    static final class TypeList {
        final int[] indices;
        final int size;

        TypeList(int[] indices, int size) {
            this.indices = indices;
            this.size = size;
        }
    }

    static final class AnnotationSet {
        final int end;
        final List<Integer> items;

        AnnotationSet(int end, List<Integer> items) {
            this.end = end;
            this.items = items;
        }
    }

    static final class AnnotationDirectory {
        final int size;
        final List<Integer> setOffsets;

        AnnotationDirectory(int size, List<Integer> setOffsets) {
            this.size = size;
            this.setOffsets = setOffsets;
        }
    }

    static final class AnnotationTotal {
        final int size;
        final List<Integer> offsets;

        AnnotationTotal(int size, List<Integer> offsets) {
            this.size = size;
            this.offsets = offsets;
        }
    }

    static final class DebugInfo {
        final int end;
        final List<Integer> names;

        DebugInfo(int end, List<Integer> names) {
            this.end = end;
            this.names = names;
        }
    }

    static final class CodeItem {
        final int size;
        final int debugOff;
        final int insnsSize;

        CodeItem(int size, int debugOff, int insnsSize) {
            this.size = size;
            this.debugOff = debugOff;
            this.insnsSize = insnsSize;
        }
    }

    static final class ClassData {
        final int size;
        final List<int[]> fields;
        final List<int[]> methods;

        ClassData(int size, List<int[]> fields, List<int[]> methods) {
            this.size = size;
            this.fields = fields;
            this.methods = methods;
        }
    }

    private static final class ClassRecord {
        final String descriptor;
        final Set<Integer> strings = new HashSet<>();
        final Set<Integer> types = new HashSet<>();
        final Set<Integer> fields = new HashSet<>();
        final Set<Integer> methods = new HashSet<>();
        final Set<Integer> protos = new HashSet<>();
        final SizeBreakdown breakdown = new SizeBreakdown();
        final List<String> semantic = new ArrayList<>();
        boolean partial;
        String warning = "";
        int methodCount;
        int fieldCount;

        ClassRecord(String descriptor) {
            this.descriptor = descriptor;
            this.breakdown.defItem = 32;
        }
    }
}
