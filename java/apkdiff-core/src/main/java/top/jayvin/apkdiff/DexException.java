package top.jayvin.apkdiff;

/** Raised when a dex structure cannot be parsed. */
public class DexException extends RuntimeException {
    public DexException(String message) {
        super(message);
    }
}
