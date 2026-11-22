package top.jayvin.apkdiff;

import java.util.LinkedHashMap;

/**
 * Where the bytes attributed to a single class came from.
 *
 * <p>The fields are mutable because the DEX parser fills one instance per class while it
 * walks the file.</p>
 */
public class SizeBreakdown {
    public long defItem;
    public long classData;
    public long code;
    public long debugInfo;
    public long annotations;
    public long staticValues;
    public long identifiers;
    public long strings;
    public long typeLists;

    public SizeBreakdown() {
    }

    public SizeBreakdown(
            long defItem,
            long classData,
            long code,
            long debugInfo,
            long annotations,
            long staticValues,
            long identifiers,
            long strings,
            long typeLists) {
        this.defItem = defItem;
        this.classData = classData;
        this.code = code;
        this.debugInfo = debugInfo;
        this.annotations = annotations;
        this.staticValues = staticValues;
        this.identifiers = identifiers;
        this.strings = strings;
        this.typeLists = typeLists;
    }

    /** Key order matches the JSON report and the Python implementation. */
    public LinkedHashMap<String, Long> asMap() {
        LinkedHashMap<String, Long> map = new LinkedHashMap<>();
        map.put("def_item", defItem);
        map.put("class_data", classData);
        map.put("code", code);
        map.put("debug_info", debugInfo);
        map.put("annotations", annotations);
        map.put("static_values", staticValues);
        map.put("identifiers", identifiers);
        map.put("strings", strings);
        map.put("type_lists", typeLists);
        return map;
    }

    public long total() {
        return defItem + classData + code + debugInfo + annotations
                + staticValues + identifiers + strings + typeLists;
    }

    public SizeBreakdown plus(SizeBreakdown other) {
        return new SizeBreakdown(
                defItem + other.defItem,
                classData + other.classData,
                code + other.code,
                debugInfo + other.debugInfo,
                annotations + other.annotations,
                staticValues + other.staticValues,
                identifiers + other.identifiers,
                strings + other.strings,
                typeLists + other.typeLists);
    }
}
