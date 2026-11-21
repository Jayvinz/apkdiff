"""Build two tiny real APKs (v1/v2) for end-to-end testing.

Requires javac + Android SDK build-tools (aapt, d8). This is a *test helper*,
not part of the apkdiff runtime.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixtures"
SDK = Path(os.environ.get("ANDROID_HOME", "D:/Android/Sdk"))
BUILD_TOOLS = SDK / "build-tools" / "34.0.0"
ANDROID_JAR = SDK / "platforms" / "android-34" / "android.jar"
D8_JAR = BUILD_TOOLS / "lib" / "d8.jar"
AAPT = BUILD_TOOLS / "aapt.exe"
JAVA = shutil.which("java") or "java"
JAVAC = shutil.which("javac") or "javac"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(str(c) for c in cmd)
    print(f"$ {printable}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {printable}")


MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.demo"
    android:versionCode="1"
    android:versionName="1.0">
    <application />
</manifest>
"""

STRINGS_V1 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Demo</string>
    <string name="welcome">Welcome</string>
</resources>
"""

STRINGS_V2 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Demo v2</string>
    <string name="welcome">Welcome</string>
    <string name="new_label">A brand new string that is fairly long so it changes size</string>
</resources>
"""

JAVA_A_V1 = """package p;
public class a {
    public int alpha(int x) { return x + 1; }
    public String beta() { return "hello"; }
}
"""

JAVA_A_V2 = """package p;
public class a {
    public int alpha(int x) { return x + 1; }
    public String beta() { return "hello"; }
    public long gamma(String value) {
        long total = 0;
        for (int i = 0; i < value.length(); i++) total += value.charAt(i);
        return total;
    }
    private int delta = 42;
}
"""

JAVA_B = """package p;
public class b {
    public int compute(int a, int b) { return a * b + 7; }
}
"""

JAVA_C = """package p;
public class c {
    public String removed() { return "this class is removed in v2"; }
}
"""

JAVA_D = """package p;
public class d {
    public String added() { return "a completely new class with a longer message"; }
    public int[] data() { return new int[] {1, 2, 3, 4, 5}; }
}
"""

MAPPING_V1 = """com.example.Alpha -> p.a:
com.example.Beta -> p.b:
com.example.Gamma -> p.c:
"""

MAPPING_V2 = """com.example.Alpha -> p.a:
com.example.Beta -> p.b:
com.example.Delta -> p.d:
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(version: str, java_sources: dict[str, str], strings: str,
          raw_files: dict[str, str], assets: dict[str, str]) -> Path:
    base = ROOT / version
    if base.exists():
        shutil.rmtree(base)
    src = base / "src"
    for rel, text in java_sources.items():
        write(src / rel, text)
    write(base / "AndroidManifest.xml", MANIFEST)
    write(base / "res" / "values" / "strings.xml", strings)
    for rel, text in raw_files.items():
        write(base / "res" / "raw" / rel, text)
    for rel, text in assets.items():
        write(base / "assets" / rel, text)

    classes = base / "classes"
    classes.mkdir(parents=True)
    java_files = [str(p) for p in src.rglob("*.java")]
    run([JAVAC, "--release", "8", "-g", "-d", str(classes), *java_files])

    dex_out = base / "dexout"
    dex_out.mkdir(parents=True)
    class_files = [str(p) for p in classes.rglob("*.class")]
    run([JAVA, "-cp", str(D8_JAR), "com.android.tools.r8.D8",
         "--lib", str(ANDROID_JAR), "--min-api", "21",
         "--output", str(dex_out), *class_files])

    apk = base / f"{version}.apk"
    run([str(AAPT), "package", "-f",
         "-M", str(base / "AndroidManifest.xml"),
         "-S", str(base / "res"),
         "-A", str(base / "assets"),
         "-I", str(ANDROID_JAR),
         "-F", str(apk)])

    import zipfile

    with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex_out / "classes.dex", "classes.dex")
    print(f"built {apk} ({apk.stat().st_size} bytes)")
    return apk


def main() -> None:
    if not AAPT.exists() or not D8_JAR.exists():
        raise SystemExit(f"Android SDK toolchain not found under {SDK}")
    ROOT.mkdir(parents=True, exist_ok=True)
    build(
        "v1",
        {"p/a.java": JAVA_A_V1, "p/b.java": JAVA_B, "p/c.java": JAVA_C},
        STRINGS_V1,
        {"data.txt": "v1 payload content\n" * 8},
        {"config.json": '{"feature":false,"items":1}\n'},
    )
    build(
        "v2",
        {"p/a.java": JAVA_A_V2, "p/b.java": JAVA_B, "p/d.java": JAVA_D},
        STRINGS_V2,
        {"data.txt": "v1 payload content\n" * 8, "extra.txt": "extra resource " * 12},
        {"config.json": '{"feature":true,"items":2,"timeout":30000}\n'},
    )
    write(ROOT / "v1" / "mapping.txt", MAPPING_V1)
    write(ROOT / "v2" / "mapping.txt", MAPPING_V2)
    print("fixtures ready:", ROOT)


if __name__ == "__main__":
    main()
