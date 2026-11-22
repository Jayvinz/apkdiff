package top.jayvin.apkdiff;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** Shared helpers: byte-size formatting and SHA-256. */
public final class Util {
    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private Util() {
    }

    /**
     * Format a byte count with KB as the smallest unit and 2 decimals.
     *
     * <p>Values below 1 KB still render as e.g. "0.25 KB", and signed values carry a
     * leading "+" or "-".</p>
     */
    private static String human(Long num, boolean signed) {
        if (num == null) {
            return "-";
        }
        String sign;
        if (signed && num > 0) {
            sign = "+";
        } else if (num < 0) {
            sign = "-";
        } else {
            sign = "";
        }
        double n = Math.abs(num.doubleValue()) / 1024.0;
        String[] units = {"KB", "MB", "GB", "TB"};
        for (int i = 0; i < units.length; i++) {
            if (n < 1024.0 || units[i].equals("TB")) {
                return sign + twoDecimals(n) + " " + units[i];
            }
            n /= 1024.0;
        }
        return sign + twoDecimals(n) + " TB";
    }

    /** Two-decimal formatting using round-half-even, matching Python's format spec. */
    private static String twoDecimals(double value) {
        return new BigDecimal(value).setScale(2, RoundingMode.HALF_EVEN).toPlainString();
    }

    /** Human readable size, e.g. 0.25 KB / 7.51 KB / 90.85 KB. */
    public static String humanSize(Long num) {
        return human(num, false);
    }

    /** Signed human readable size change, e.g. +7.51 KB / -0.25 KB. */
    public static String humanDelta(Long num) {
        return human(num, true);
    }

    /** Combine two optional warning strings with the parser's " | " separator. */
    static String joinNonEmpty(String first, String second) {
        if (first.isEmpty()) {
            return second;
        }
        if (second.isEmpty()) {
            return first;
        }
        return first + " | " + second;
    }

    /** SHA-256 of the given bytes, lowercase hex. */
    public static String sha256Hex(byte[] data) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return toHex(digest.digest(data));
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256 unavailable", exc);
        }
    }

    static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            int value = b & 0xff;
            sb.append(HEX[value >>> 4]).append(HEX[value & 0x0f]);
        }
        return sb.toString();
    }
}
