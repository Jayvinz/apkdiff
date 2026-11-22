package top.jayvin.apkdiff;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Minimal deterministic JSON writer (pretty printed, UTF-8 raw, Python-compatible layout). */
final class JsonWriter {
    private JsonWriter() {
    }

    static String write(Object value) {
        return write(value, 2);
    }

    static String write(Object value, int indent) {
        StringBuilder sb = new StringBuilder();
        append(sb, value, 0, indent);
        return sb.toString();
    }

    private static void append(StringBuilder sb, Object value, int level, int indent) {
        if (value == null) {
            sb.append("null");
        } else if (value instanceof Boolean) {
            sb.append(((Boolean) value) ? "true" : "false");
        } else if (value instanceof Number) {
            sb.append(number((Number) value));
        } else if (value instanceof String) {
            appendString(sb, (String) value);
        } else if (value instanceof Map) {
            appendMap(sb, (Map<?, ?>) value, level, indent);
        } else if (value instanceof Iterable) {
            appendIterable(sb, (Iterable<?>) value, level, indent);
        } else {
            appendString(sb, value.toString());
        }
    }

    private static void appendMap(StringBuilder sb, Map<?, ?> value, int level, int indent) {
        if (value.isEmpty()) {
            sb.append("{}");
            return;
        }
        sb.append("{\n");
        List<Map.Entry<?, ?>> entries = new ArrayList<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            entries.add(entry);
        }
        for (int i = 0; i < entries.size(); i++) {
            Map.Entry<?, ?> entry = entries.get(i);
            sb.append(" ".repeat(indent * (level + 1)));
            appendString(sb, String.valueOf(entry.getKey()));
            sb.append(": ");
            append(sb, entry.getValue(), level + 1, indent);
            if (i != entries.size() - 1) {
                sb.append(",");
            }
            sb.append("\n");
        }
        sb.append(" ".repeat(indent * level)).append("}");
    }

    private static void appendIterable(StringBuilder sb, Iterable<?> value, int level, int indent) {
        List<Object> items = new ArrayList<>();
        for (Object item : value) {
            items.add(item);
        }
        if (items.isEmpty()) {
            sb.append("[]");
            return;
        }
        sb.append("[\n");
        for (int i = 0; i < items.size(); i++) {
            sb.append(" ".repeat(indent * (level + 1)));
            append(sb, items.get(i), level + 1, indent);
            if (i != items.size() - 1) {
                sb.append(",");
            }
            sb.append("\n");
        }
        sb.append(" ".repeat(indent * level)).append("]");
    }

    private static String number(Number value) {
        if (value instanceof Double) {
            double d = value.doubleValue();
            if (d == (double) (long) d) {
                return Long.toString((long) d) + ".0";
            }
            return Double.toString(d);
        }
        if (value instanceof Float) {
            float f = value.floatValue();
            if (f == (float) (long) f) {
                return Long.toString((long) f) + ".0";
            }
            return Float.toString(f);
        }
        return value.toString();
    }

    private static void appendString(StringBuilder sb, String value) {
        sb.append('"');
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\b':
                    sb.append("\\b");
                    break;
                case '\u000c':
                    sb.append("\\f");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (ch < 0x20) {
                        sb.append("\\u")
                                .append(String.format(java.util.Locale.ROOT, "%04x", (int) ch));
                    } else {
                        sb.append(ch);
                    }
                    break;
            }
        }
        sb.append('"');
    }
}
