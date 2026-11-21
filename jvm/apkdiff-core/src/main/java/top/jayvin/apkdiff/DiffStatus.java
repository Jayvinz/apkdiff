package top.jayvin.apkdiff;

/** Change status constants and their Chinese labels. */
public final class DiffStatus {
    public static final String ADDED = "added";
    public static final String DELETED = "deleted";
    public static final String MODIFIED = "modified";
    public static final String RENAMED = "renamed";
    public static final String UNCHANGED = "unchanged";

    private DiffStatus() {
    }

    public static String label(String status) {
        switch (status) {
            case ADDED:
                return "新增";
            case DELETED:
                return "删除";
            case MODIFIED:
                return "修改";
            case RENAMED:
                return "重命名";
            case UNCHANGED:
                return "未变";
            default:
                return status;
        }
    }
}
