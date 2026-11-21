"""Generate two realistic, moderately complex Android APKs for apkdiff testing.

Test helper only (not part of the apkdiff runtime). Requires JDK + Android SDK
with build-tools (aapt, d8) and a platform android.jar.

The generated project mimics an obfuscated e-commerce app:

* ~40 classes across 6 packages with layering (ui / domain / data / util)
* enums, interfaces with default methods, annotations, inner + anonymous
  classes, lambdas, generics, static initializers, switch and try/catch
* two dex files (multidex) built separately with a shared lib jar
* a real R8-style mapping.txt (class names are obfuscated in the dex)
* rich resources: values, layouts, drawables, mipmap PNG, SVG, raw,
  assets JSON/SVG/SQLite DB, native libs
* controlled v1 -> v2 changes: added / deleted / modified classes and resources,
  plus a content-identical resource rename for --detect-renames
"""

from __future__ import annotations

import os
import random
import shutil
import sqlite3
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixtures" / "complex"
SDK = Path(os.environ.get("ANDROID_HOME", "D:/Android/Sdk"))
BUILD_TOOLS = SDK / "build-tools" / "34.0.0"
ANDROID_JAR = SDK / "platforms" / "android-34" / "android.jar"
D8_JAR = BUILD_TOOLS / "lib" / "d8.jar"
AAPT = BUILD_TOOLS / "aapt.exe"
JAVA = shutil.which("java") or "java"
JAVAC = shutil.which("javac") or "javac"
JAR = shutil.which("jar") or "jar"

# ---------------------------------------------------------------------------
# class catalog: (obfuscated name, original name, role, in_v1, in_v2, v2 patch)
# ---------------------------------------------------------------------------

CATALOG: list[tuple[str, str, str, bool, bool, str]] = [
    # --- package a : app / activities ---
    ("a.a", "com.shop.app.ShopApplication", "app", True, True,
     "    public int version() { return 2; }\n"
     "    private static final String BUILD = \"v2-release\";\n"
     "    public String build() { return BUILD; }\n"),
    ("a.b", "com.shop.ui.MainActivity", "activity", True, True,
     "    public String greeting(String user) {\n"
     "        StringBuilder sb = new StringBuilder(\"Welcome back, \");\n"
     "        sb.append(user).append(\"! Your cart has \").append(count).append(\" items.\");\n"
     "        return sb.toString();\n"
     "    }\n"),
    ("a.c", "com.shop.ui.ProductListActivity", "activity", True, True, ""),
    ("a.d", "com.shop.ui.ProductDetailActivity", "activity", True, True, ""),
    ("a.e", "com.shop.ui.CartActivity", "activity", True, False, ""),
    ("a.f", "com.shop.ui.SearchActivity", "activity", False, True, ""),

    # --- package b : fragments / adapters ---
    ("b.a", "com.shop.ui.adapter.ProductAdapter", "adapter", True, True, ""),
    ("b.b", "com.shop.ui.adapter.CartAdapter", "adapter", True, True, ""),
    ("b.c", "com.shop.ui.fragment.HomeFragment", "fragment", True, True, ""),
    ("b.d", "com.shop.ui.fragment.ProfileFragment", "fragment", True, False, ""),
    ("b.e", "com.shop.ui.adapter.FilterAdapter", "adapter", False, True, ""),

    # --- package c : domain ---
    ("c.a", "com.shop.domain.model.Product", "model", True, True,
     "    private String subtitle;\n"
     "    public String getSubtitle() { return subtitle; }\n"
     "    public void setSubtitle(String s) { this.subtitle = s; }\n"),
    ("c.b", "com.shop.domain.model.CartItem", "model", True, True, ""),
    ("c.c", "com.shop.domain.model.Order", "model", True, True, ""),
    ("c.d", "com.shop.domain.model.OrderStatus", "enum", True, True, ""),
    ("c.e", "com.shop.domain.usecase.GetProductsUseCase", "usecase", True, True, ""),
    ("c.f", "com.shop.domain.usecase.AddToCartUseCase", "usecase", True, True, ""),
    ("c.g", "com.shop.domain.usecase.CheckoutUseCase", "usecase", True, True, ""),

    # --- package d : data ---
    ("d.a", "com.shop.domain.repository.ProductRepository", "interface", True, True, ""),
    ("d.b", "com.shop.domain.repository.CartRepository", "interface", True, True, ""),
    ("d.c", "com.shop.data.repository.ProductRepositoryImpl", "impl", True, True,
     "    public String diagnostics(int code) {\n"
     "        try {\n"
     "            if (code < 0) throw new IllegalArgumentException(\"bad code\");\n"
     "            return \"ok:\" + code;\n"
     "        } catch (IllegalArgumentException ex) {\n"
     "            return \"bad:\" + ex.getMessage();\n"
     "        } catch (RuntimeException ex) {\n"
     "            return \"runtime\";\n"
     "        }\n"
     "    }\n"),
    ("d.d", "com.shop.data.repository.CartRepositoryImpl", "impl", True, True, ""),
    ("d.e", "com.shop.data.local.DatabaseHelper", "helper", True, True, ""),
    ("d.f", "com.shop.data.local.UserDao", "interface", True, True, ""),
    ("d.g", "com.shop.data.remote.ApiService", "interface", True, True, ""),
    ("d.h", "com.shop.data.remote.NetworkClient", "impl", True, True, ""),
    ("d.i", "com.shop.data.remote.dto.ProductDto", "dto", True, True, ""),
    ("d.j", "com.shop.data.remote.dto.OrderDto", "dto", True, True, ""),

    # --- package e : util ---
    ("e.a", "com.shop.util.Logger", "util", True, True, ""),
    ("e.b", "com.shop.util.MoneyFormatter", "util", True, True,
     "    public static String formatCents(long cents, String currency) {\n"
     "        return currency + format(cents);\n"
     "    }\n"),
    ("e.c", "com.shop.util.Validator", "util", True, True, ""),
    ("e.d", "com.shop.util.Constants", "constants", True, True, ""),
    ("e.tr", "com.shop.common.Traceable", "annotation", True, True, ""),
    ("e.f", "com.shop.util.DateTimeUtils", "util", True, True, ""),
    ("e.g", "com.shop.util.StringUtils", "util", True, True, ""),
    ("e.h", "com.shop.util.CollectionUtils", "util", True, True, ""),

    # --- package f : new in v2 ---
    ("f.a", "com.shop.analytics.AnalyticsHelper", "util", False, True, ""),
    ("f.b", "com.shop.feature.NewFeatureController", "controller", False, True, ""),
]

# dex assignment: package prefix -> dex index (classes.dex / classes2.dex / ...)
DEX_GROUPS: dict[int, set[str]] = {
    1: {"a", "b", "g", "h", "i"},
    2: {"c", "d", "e", "f", "j", "k", "l", "m"},
    3: {"n", "o", "p", "q", "r", "s"},
}


def _letter_codes(count: int) -> list[str]:
    """a, b, ..., z, aa, ab, ... for generated class names."""
    out: list[str] = []
    for i in range(count):
        value = i
        chars: list[str] = []
        while True:
            chars.append(chr(ord("a") + value % 26))
            value = value // 26 - 1
            if value < 0:
                break
        out.append("".join(reversed(chars)))
    return out


# Scaled-up business modules. Each domain gets one interface, its impl, and a
# spread of realistic layers (model/dto/usecase/viewmodel/adapter/...).
ROLE_PLAN: list[tuple[str, str]] = [
    ("interface", "Repository"), ("impl", "RepositoryImpl"),
    ("model", "Entity"), ("dto", "Dto"), ("usecase", "UseCase"),
    ("viewmodel", "ViewModel"), ("adapter", "Adapter"), ("fragment", "Fragment"),
    ("util", "Utils"), ("cache", "Cache"), ("mapper", "Mapper"),
    ("validator", "Validator"), ("service", "Service"), ("event", "Event"),
    ("worker", "Worker"),
]

DOMAIN_SPECS: list[tuple[str, str]] = [
    ("g", "catalog"), ("h", "cart"), ("i", "checkout"), ("j", "user"),
    ("k", "social"), ("l", "media"), ("m", "push"), ("n", "analytics"),
    ("o", "network"), ("p", "storage"), ("q", "ui"), ("r", "helper"),
]

# (domain package, suffix) pairs removed in v2 and classes modified in v2
REMOVED_IN_V2 = {("h", "Validator"), ("k", "Event"), ("k", "Worker"),
                 ("l", "Mapper"), ("o", "Dto"), ("p", "Cache")}
MODIFIED_ROLES = {"model", "dto", "usecase", "viewmodel", "service",
                  "cache", "mapper", "worker", "adapter"}

EXPECTED_ADDED: list[str] = []
EXPECTED_DELETED: list[str] = []
EXPECTED_MODIFIED: list[str] = []


def _extend_catalog() -> None:
    letters = _letter_codes(len(ROLE_PLAN))
    for pkg, domain in DOMAIN_SPECS:
        for (role, suffix), letter in zip(ROLE_PLAN, letters):
            obf = f"{pkg}.{letter}"
            orig = f"com.shop.{domain}.{suffix}"
            in_v2 = (pkg, suffix) not in REMOVED_IN_V2
            patch = ""
            if in_v2 and role in MODIFIED_ROLES and (ord(pkg) + len(suffix)) % 4 == 0:
                patch = (f'    public String extraInfo() {{ return "{orig} v2"; }}\n'
                         f'    private int v2Counter;\n')
                EXPECTED_MODIFIED.append(orig)
            if not in_v2:
                EXPECTED_DELETED.append(orig)
            CATALOG.append((obf, orig, role, True, in_v2, patch))

    # brand-new v2-only module (15 classes) to exercise large additions
    for (role, suffix), letter in zip(ROLE_PLAN, letters):
        obf = f"s.{letter}"
        orig = f"com.shop.explore.{suffix}"
        CATALOG.append((obf, orig, role, False, True, ""))
        EXPECTED_ADDED.append(orig)


_extend_catalog()

# curated classes also participate in the expected-change manifest
EXPECTED_ADDED += [
    "com.shop.ui.SearchActivity",
    "com.shop.ui.adapter.FilterAdapter",
    "com.shop.analytics.AnalyticsHelper",
    "com.shop.feature.NewFeatureController",
]
EXPECTED_DELETED += [
    "com.shop.ui.CartActivity",
    "com.shop.ui.fragment.ProfileFragment",
]
EXPECTED_MODIFIED += [
    "com.shop.app.ShopApplication",
    "com.shop.ui.MainActivity",
    "com.shop.domain.model.Product",
    "com.shop.data.repository.ProductRepositoryImpl",
    "com.shop.util.MoneyFormatter",
]

# Expected resource statuses (with --detect-renames enabled). These are the
# entry names as they appear *inside the APK*: aapt compiles res/values/*.xml
# into resources.arsc (so they are not entries) and renames mipmap-xxhdpi to
# mipmap-xxhdpi-v4. Every per-domain resource carries a -v1/-v2 marker so it
# shows up as modified; the XML ones also shift when resource IDs change.
ALL_DOMAINS = [
    "catalog", "cart", "checkout", "user", "social", "media",
    "push", "analytics", "network", "storage", "ui", "helper",
]
EXPECTED_RES: dict[str, list[str]] = {
    "added": [
        "assets/databases/explore.db", "assets/explore/config.json",
        "assets/images/explore.svg", "assets/nested/ui/new_pref.json",
        "lib/mips/libshop.so", "res/drawable/bg_accent.xml",
        "res/drawable/bg_explore.xml", "res/layout/activity_search.xml",
        "res/layout/item_explore.xml", "res/raw/explore_config.json",
        "res/raw/help.txt",
    ],
    "deleted": [
        "assets/images/legacy.svg", "assets/web/index.html",
        "lib/armeabi-v7a/libshop.so", "res/layout/fragment_home.xml",
        "res/raw/legal_notice.txt",
    ],
    "modified": [
        "AndroidManifest.xml", "assets/app-config.json",
        "assets/databases/app.db", "assets/images/hero.svg",
        "lib/arm64-v8a/libshop.so", "lib/arm64-v8a/libshop_core.so",
        "res/layout/activity_main.xml", "res/layout/item_product.xml",
        "res/mipmap-xxhdpi-v4/ic_launcher.png", "res/raw/catalog.bin",
        "res/raw/logo.svg", "resources.arsc",
    ],
    "renamed": ["res/raw/settings.json"],
}
for _domain in ALL_DOMAINS:
    EXPECTED_RES["modified"] += [
        f"assets/{_domain}/config.json",
        f"res/drawable/bg_{_domain}.xml",
        f"res/layout/item_{_domain}.xml",
        f"res/raw/{_domain}_config.json",
    ]


# ---------------------------------------------------------------------------
# Java source templates ($ORIG / $OBF / $EXTRA are plain placeholders)
# ---------------------------------------------------------------------------

def javadoc(orig: str) -> str:
    return f"/** Original: {orig} */"


TEMPLATES: dict[str, str] = {
    "app": """package a;

$JAVADOC
public class $CLS {
    private static final int[] TABLE = {1, 2, 3, 5, 8, 13, 21, 34, 55, 89};
    private static final String APP_NAME = "Shop-$OBF";
    static {
        System.out.println(APP_NAME + TABLE.length);
    }
    public $CLS() { }
    public String info() { return APP_NAME + ":" + TABLE[4]; }
$EXTRA}
""",

    "activity": """package a;

$JAVADOC
public class $CLS {
    private final String tag = "$OBF-activity";
    private int count = 3;
    public $CLS() { }
    public String build(int mode) {
        StringBuilder sb = new StringBuilder(tag);
        try {
            switch (mode) {
                case 1: sb.append(":one"); break;
                case 2: sb.append(":two"); break;
                case 100: sb.append(":hundred"); break;
                default: sb.append(":unknown-").append(mode);
            }
        } catch (RuntimeException ex) {
            sb.append(":runtime");
        } catch (Throwable t) {
            sb.append(":fatal");
        }
        for (int i = 0; i < count; i++) sb.append(i);
        return sb.toString();
    }
    public long total(long price, int qty) { return price * qty + 99L; }
$EXTRA}
""",

    "adapter": """package b;

import java.util.ArrayList;
import java.util.List;

$JAVADOC
public class $CLS<T> {
    private final List<T> items = new ArrayList<T>();
    private String title = "$OBF";
    public void add(T item) { items.add(item); }
    public int size() { return items.size(); }
    public String join() {
        StringBuilder out = new StringBuilder(title);
        for (T item : items) out.append('|').append(String.valueOf(item));
        return out.toString();
    }
    public Runnable task() { return () -> System.out.println("adapter " + size()); }
    public static class Holder {
        int id; String label;
        public Holder(int id, String label) { this.id = id; this.label = label; }
    }
$EXTRA}
""",

    "fragment": """package b;

$JAVADOC
public class $CLS {
    static final class Holder {
        int id; String label;
        Holder(int id, String label) { this.id = id; this.label = label; }
    }
    public Object create() {
        Runnable r = new Runnable() {
            public void run() { System.out.println("$OBF fragment"); }
        };
        r.run();
        return new Holder(1, "home");
    }
    public String render(int type) {
        switch (type) {
            case 0: return "home";
            case 7: return "profile";
            case 42: return "settings";
            default: return "other";
        }
    }
$EXTRA}
""",

    "model": """package c;

$JAVADOC
public class $CLS {
    private long id;
    private String name;
    private double price;
    private boolean available;
    public $CLS(long id, String name, double price, boolean available) {
        this.id = id; this.name = name; this.price = price; this.available = available;
    }
    public long getId() { return id; }
    public void setId(long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public double getPrice() { return price; }
    public void setPrice(double price) { this.price = price; }
    public boolean isAvailable() { return available; }
    public void setAvailable(boolean available) { this.available = available; }
    public String describe() { return name + " / " + price + " / " + available; }
$EXTRA}
""",

    "enum": """package c;

$JAVADOC
public enum $CLS {
    CREATED, PAID, SHIPPED, CLOSED;
    public boolean terminal() { return this == SHIPPED || this == CLOSED; }
    public static $CLS parse(int value) {
        switch (value) {
            case 1: return CREATED;
            case 2: return PAID;
            case 3: return SHIPPED;
            case 4: return CLOSED;
            default: return CREATED;
        }
    }
$EXTRA}
""",

    "usecase": """package c;

import java.util.ArrayList;
import java.util.List;

$JAVADOC
public class $CLS {
    private final List<String> errors = new ArrayList<String>();
    public String execute(String input) {
        if (input == null || input.length() == 0) {
            errors.add("empty input");
            return "";
        }
        StringBuilder sb = new StringBuilder(input);
        for (int i = 0; i < input.length(); i += 2) sb.append(input.charAt(i));
        return sb.toString();
    }
    public int errorCount() { return errors.size(); }
$EXTRA}
""",

    "interface": """package d;

import java.util.List;

$JAVADOC
public interface $CLS {
    List<Object> load();
    int count();
    default String label() { return "$OBF-repository"; }
}
""",

    "impl": """package d;

import java.util.ArrayList;
import java.util.List;

$JAVADOC
public class $CLS implements a {
    private final List<Object> cache = new ArrayList<Object>();
    public List<Object> load() { return cache; }
    public int count() { return cache.size(); }
    public void store(Object value) { cache.add(value); }
    public String sparse(int code) {
        try {
            switch (code) {
                case 1: return "one";
                case 50: return "fifty";
                case 1000: return "thousand";
                default: return "none";
            }
        } catch (Throwable t) {
            return "error";
        }
    }
$EXTRA}
""",

    "helper": """package d;

$JAVADOC
public class $CLS {
    private static final String SCHEMA = "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT);";
    public String schema() { return SCHEMA; }
    public int migrate(int from) {
        int version = from;
        while (version < 5) { version++; }
        return version;
    }
$EXTRA}
""",

    "dto": """package d;

$JAVADOC
public class $CLS {
    private String id;
    private String name;
    private long timestamp;
    public $CLS(String id, String name, long timestamp) {
        this.id = id; this.name = name; this.timestamp = timestamp;
    }
    public Object toMap() {
        StringBuilder sb = new StringBuilder("{");
        sb.append("id=").append(id).append(",name=").append(name);
        sb.append(",ts=").append(timestamp).append("}");
        return sb.toString();
    }
$EXTRA}
""",

    "util": """package e;

$JAVADOC
public class $CLS {
    private static final String PREFIX = "$OBF";
    public static String format(long value) {
        StringBuilder sb = new StringBuilder(PREFIX);
        sb.append(':').append(value);
        return sb.toString();
    }
    public static boolean check(String s) {
        return s != null && s.length() > 0 && s.length() < 256;
    }
$EXTRA}
""",

    "constants": """package e;

$JAVADOC
public final class $CLS {
    public static final String BASE_URL = "https://api.example.com/v2/catalog";
    public static final int TIMEOUT_MS = 30000;
    public static final int MAX_RETRIES = 3;
    public static final String[] FEATURE_FLAGS = {"search", "checkout", "profile", "dark_mode"};
    private $CLS() { }
$EXTRA}
""",

    "annotation": """package e;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

$JAVADOC
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.FIELD})
public @interface $CLS {
    String value() default "";
    int priority() default 0;
    String[] tags() default {};
}
""",

    "controller": """package f;

$JAVADOC
public class $CLS {
    public String handle(int code) {
        switch (code) {
            case 200: return "ok";
            case 404: return "missing";
            case 500: return "error";
            default: return "unknown";
        }
    }
    public int score(String input) {
        int total = 0;
        for (int i = 0; i < input.length(); i++) total += input.charAt(i) * (i + 1);
        return total;
    }
$EXTRA}
""",
}

# Extra role templates used by the scaled-up business modules. Kept separate
# from the curated set above so the hand-written classes stay easy to read
# while the bulk of the project is generated.
TEMPLATES.update({
    "viewmodel": """package $PKG;

import java.util.ArrayList;
import java.util.List;

$JAVADOC
public class $CLS {
    private final List<String> state = new ArrayList<String>();
    private int version;
    public void update(String value) { state.add(value); version++; }
    public String render() { return "$OBF:" + version + ":" + state.size(); }
    public Runnable refresh() { return () -> System.out.println(render()); }
    public int pending() { return state.size() * 3 + version; }
$EXTRA}
""",
    "cache": """package $PKG;

import java.util.HashMap;
import java.util.Map;

$JAVADOC
public class $CLS {
    private final Map<String, Object> store = new HashMap<String, Object>();
    private long hits;
    public void put(String key, Object value) { store.put(key, value); }
    public Object get(String key) { hits++; return store.get(key); }
    public int size() { return store.size(); }
    public String stats() { return "$OBF:" + size() + ":" + hits; }
$EXTRA}
""",
    "mapper": """package $PKG;

$JAVADOC
public class $CLS {
    public String apply(String input) {
        if (input == null) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            sb.append(Character.toUpperCase(c));
        }
        return sb.toString();
    }
    public int mapCode(int code) { return code * 31 + 7; }
$EXTRA}
""",
    "validator": """package $PKG;

$JAVADOC
public class $CLS {
    public boolean validate(String value) {
        try {
            if (value == null || value.length() < 3) return false;
            return value.indexOf(' ') < 0;
        } catch (RuntimeException ex) {
            return false;
        }
    }
    public int score(String input) {
        int total = 0;
        for (char c : input.toCharArray()) total += c;
        return total;
    }
$EXTRA}
""",
    "service": """package $PKG;

import java.util.ArrayList;
import java.util.List;

$JAVADOC
public class $CLS {
    private final List<String> log = new ArrayList<String>();
    public String process(String request) {
        log.add(request);
        try {
            switch (request.length() % 4) {
                case 0: return "accepted";
                case 1: return "pending";
                case 2: return "rejected";
                default: return "retry";
            }
        } catch (Throwable t) {
            return "failed";
        }
    }
    public int logSize() { return log.size(); }
$EXTRA}
""",
    "event": """package $PKG;

$JAVADOC
public class $CLS {
    private final String type = "$OBF";
    private final long timestamp;
    public $CLS(long timestamp) { this.timestamp = timestamp; }
    public String payload() { return type + ":" + timestamp; }
    public long elapsed(long now) { return now - timestamp; }
$EXTRA}
""",
    "worker": """package $PKG;

$JAVADOC
public class $CLS {
    public int run(int[] data) {
        int total = 0;
        try {
            for (int i = 0; i < data.length; i++) total += data[i] * (i + 1);
        } catch (RuntimeException ex) {
            return -1;
        }
        return total;
    }
    public String name() { return "$OBF-worker"; }
$EXTRA}
""",
})


import re as _re

# CLASS-retention annotations applied to a few classes so the DEX parser has
# real annotation directories / encoded values (string, int, string[]).
ANNOTATIONS: dict[str, str] = {
    "e.a": '@tr(value="logger", priority=2, tags={"net", "debug"})',
    "c.a": '@e.tr(value="product", priority=5, tags={"domain", "catalog"})',
    "a.b": '@e.tr(value="main", priority=1)',
}

# Templates originally hard-code a package for readability; make them generic
# so classes added in v2 (package f) can reuse util/controller templates.
for _role, _src in list(TEMPLATES.items()):
    TEMPLATES[_role] = _re.sub(r"^package \w+;", "package $PKG;", _src, flags=_re.M)


def java_source(obf: str, orig: str, role: str, extra: str) -> str:
    cls = obf.split(".")[-1]
    pkg = obf.rsplit(".", 1)[0]
    template = TEMPLATES[role]
    source = (template
              .replace("$PKG", pkg)
              .replace("$ORIG", orig)
              .replace("$JAVADOC", javadoc(orig))
              .replace("$OBF", obf)
              .replace("$CLS", cls)
              .replace("$EXTRA", extra))
    ann = ANNOTATIONS.get(obf, "")
    if ann and pkg != "e":
        source = source.replace(f"package {pkg};\n", f"package {pkg};\n\nimport e.tr;\n", 1)
        ann = ann.replace("@e.tr", "@tr")
    if ann:
        for marker in ("public class ", "public interface ", "public enum "):
            if marker in source:
                source = source.replace(marker, ann + "\n" + marker, 1)
                break
    return source


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.complex"
    android:versionCode="__CODE__"
    android:versionName="__NAME__">
    <application android:label="@string/app_name" android:allowBackup="true">
        <activity android:name=".MainActivity" android:exported="true" />
        <activity android:name=".ProductListActivity" />
        <activity android:name=".ProductDetailActivity" />
    </application>
</manifest>
"""


def strings_xml(v2: bool) -> str:
    items = [
        ("app_name", "Shop Demo" if not v2 else "Shop Demo v2"),
        ("welcome", "Welcome to our shop"),
        ("product_title", "Product details"),
        ("price_label", "Price"),
        ("error_network", "Network error, please retry"),
    ]
    if v2:
        items += [("search_hint", "Search products"), ("new_badge", "NEW")]
    body = "\n".join(f'    <string name="{k}">{v}</string>' for k, v in items)
    return f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n{body}\n</resources>\n'


COLORS_V1 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#FF6200EE</color>
    <color name="accent">#FF03DAC5</color>
    <color name="background">#FFF5F5F5</color>
</resources>
"""
COLORS_V2 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#FF6200EE</color>
    <color name="accent">#FFBB86FC</color>
    <color name="background">#FFF5F5F5</color>
    <color name="warning">#FFFFA726</color>
</resources>
"""

DIMENS = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <dimen name="padding_small">8dp</dimen>
    <dimen name="padding_large">24dp</dimen>
    <dimen name="text_size">16sp</dimen>
</resources>
"""

STYLES_V1 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="android:style/Theme.Material.Light">
        <item name="android:colorPrimary">@color/primary</item>
    </style>
    <style name="TextTitle">
        <item name="android:textSize">@dimen/text_size</item>
    </style>
</resources>
"""
STYLES_V2 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="android:style/Theme.Material.Light">
        <item name="android:colorPrimary">@color/primary</item>
        <item name="android:colorAccent">@color/accent</item>
    </style>
    <style name="TextTitle">
        <item name="android:textSize">@dimen/text_size</item>
    </style>
</resources>
"""

ARRAYS_V1 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string-array name="categories">
        <item>Electronics</item><item>Books</item><item>Clothing</item>
        <item>Food</item><item>Toys</item><item>Others</item>
    </string-array>
</resources>
"""
ARRAYS_V2 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string-array name="categories">
        <item>Electronics</item><item>Books</item><item>Clothing</item>
        <item>Food</item><item>Toys</item><item>Others</item><item>Sports</item>
    </string-array>
</resources>
"""

PLURALS = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <plurals name="items_count">
        <item quantity="one">%d item</item>
        <item quantity="other">%d items</item>
    </plurals>
</resources>
"""
BOOLS = '<?xml version="1.0" encoding="utf-8"?>\n<resources><bool name="feature_x">false</bool></resources>\n'
INTEGERS = '<?xml version="1.0" encoding="utf-8"?>\n<resources><integer name="max_items">20</integer></resources>\n'

LAYOUT_MAIN_V1 = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:orientation="vertical" android:padding="@dimen/padding_large">
    <TextView android:id="@+id/title" android:text="@string/app_name" style="@style/TextTitle" />
    <Button android:id="@+id/search" android:text="Search" />
</LinearLayout>
"""
LAYOUT_MAIN_V2 = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:orientation="vertical" android:padding="@dimen/padding_large">
    <TextView android:id="@+id/title" android:text="@string/app_name" style="@style/TextTitle" />
    <Button android:id="@+id/search" android:text="@string/search_hint" />
    <TextView android:id="@+id/badge" android:text="@string/new_badge" />
</LinearLayout>
"""
LAYOUT_ITEM = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:orientation="horizontal" android:padding="@dimen/padding_small">
    <TextView android:id="@+id/name" android:text="@string/product_title" />
    <TextView android:id="@+id/price" android:text="@string/price_label" />
</LinearLayout>
"""
LAYOUT_HOME = """<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android">
    <TextView android:id="@+id/home" android:text="@string/welcome" />
</FrameLayout>
"""
LAYOUT_SEARCH = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:orientation="vertical" android:padding="@dimen/padding_small">
    <EditText android:id="@+id/query" android:hint="@string/search_hint" />
    <Button android:id="@+id/go" android:text="Go" />
</LinearLayout>
"""

DRAWABLE_V1 = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="@color/primary" />
    <corners android:radius="8dp" />
</shape>
"""
DRAWABLE_ACCENT = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="oval">
    <solid android:color="@color/accent" />
</shape>
"""

RAW_CONFIG = '{"endpoint":"https://api.example.com","retries":3,"timeout":30000,"flags":["a","b","c"]}\n'
RAW_LEGAL = "TERMS OF USE\n\nThis is a sample legal notice.\n" * 6
RAW_CATALOG_V1 = "catalog-v1:" + "x" * 600 + "\n"
RAW_CATALOG_V2 = "catalog-v2:" + "y" * 900 + "\n"
RAW_HELP = "HELP CENTER\n" * 10

ASSET_CONFIG_V1 = '{"theme":"light","language":"zh-CN","version":1}\n'
ASSET_CONFIG_V2 = '{"theme":"dark","language":"en-US","version":2,"experimental":true}\n'
ASSET_PREFS = '{"notifications":true,"syncWifiOnly":false,"fontScale":1.0}\n'
ASSET_NEW_PREFS = '{"newFeature":true,"beta":false,"threshold":12}\n'
ASSET_HTML = "<html><body><h1>Shop Help</h1><p>Welcome.</p></body></html>\n"


SVG_LOGO_V1 = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#2255ff"/>
  <text x="12" y="40" font-size="28" fill="#ffffff">v1</text>
</svg>
"""
SVG_LOGO_V2 = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#12a37a"/>
  <text x="12" y="40" font-size="28" fill="#ffffff">v2</text>
</svg>
"""
SVG_HERO_V1 = """<svg xmlns="http://www.w3.org/2000/svg" width="320" height="160" viewBox="0 0 320 160">
  <rect width="320" height="160" fill="#f4f6fb"/>
  <circle cx="80" cy="80" r="48" fill="#2255ff"/>
  <text x="150" y="90" font-size="24" fill="#1f2329">Spring sale v1</text>
</svg>
"""
SVG_HERO_V2 = """<svg xmlns="http://www.w3.org/2000/svg" width="320" height="160" viewBox="0 0 320 160">
  <rect width="320" height="160" fill="#eefbf5"/>
  <circle cx="80" cy="80" r="48" fill="#12a37a"/>
  <text x="150" y="90" font-size="24" fill="#1f2329">Summer sale v2</text>
</svg>
"""
SVG_EXPLORE = """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <rect width="96" height="96" fill="#fff4e5"/>
  <path d="M12 48 L48 12 L84 48 L48 84 Z" fill="#b76e00"/>
</svg>
"""
SVG_LEGACY = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <circle cx="24" cy="24" r="20" fill="#999999"/>
  <text x="14" y="30" font-size="16" fill="#ffffff">old</text>
</svg>
"""


def write_sqlite(path: Path, version: str, explore: bool = False) -> None:
    """Create a real SQLite database asset with deterministic rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER)")
        price = 2000 if version == "v2" else 1000
        conn.executemany(
            "INSERT INTO products (id, name, price) VALUES (?, ?, ?)",
            [(1, "product-a", price), (2, "product-b", price + 500),
             (3, "product-c", price + 900)],
        )
        if explore:
            conn.execute("CREATE TABLE explore (id INTEGER PRIMARY KEY, keyword TEXT)")
            conn.executemany(
                "INSERT INTO explore (id, keyword) VALUES (?, ?)",
                [(1, "new-arrivals"), (2, "trending")],
            )
        conn.commit()
    finally:
        conn.close()

def png_bytes(r: int, g: int, b: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes([0, r, g, b])))
    return header + ihdr + idat + chunk(b"IEND", b"")


def so_bytes(seed: int, size: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(size))


# ---------------------------------------------------------------------------
# build helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print("$ " + " ".join(str(c) for c in cmd))
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"command failed ({proc.returncode})")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_sources(version: str) -> tuple[Path, Path]:
    """Write Java sources and mapping.txt; return (src dir, mapping path)."""
    base = ROOT / version
    src = base / "src"
    if base.exists():
        shutil.rmtree(base)
    src.mkdir(parents=True)

    mapping_lines = [
        "# compiler: R8",
        "# compiler_version: 8.2.2-dev",
        "# {" + '"id":"com.android.tools.r8.mapping","version":"2.2"' + "}",
    ]
    is_v2 = version == "v2"
    for obf, orig, role, in_v1, in_v2, patch in CATALOG:
        if not (in_v2 if is_v2 else in_v1):
            continue
        extra = patch if is_v2 else ""
        source = java_source(obf, orig, role, extra)
        write(src / f"{obf.replace('.', '/')}.java", source)
        mapping_lines.append(f"{orig} -> {obf}:")
        mapping_lines.append("    1:1:void <init>() -> <init>")

    mapping = base / "mapping.txt"
    write(mapping, "\n".join(mapping_lines) + "\n")
    return src, mapping


def build_dexes(version: str, src: Path) -> list[Path]:
    base = ROOT / version
    classes = base / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    java_files = sorted(str(p) for p in src.rglob("*.java"))
    run([JAVAC, "--release", "8", "-g", "-cp", str(ANDROID_JAR),
         "-d", str(classes), *java_files])

    all_jar = base / "allclasses.jar"
    run([JAR, "cf", str(all_jar), "-C", str(classes), "."])

    class_files = sorted(classes.rglob("*.class"))
    groups: dict[int, list[Path]] = {idx: [] for idx in DEX_GROUPS}
    for cf in class_files:
        rel = cf.relative_to(classes)
        package = str(rel.parent).replace("\\", "/")
        top = package.split("/")[0] if package != "." else ""
        assigned = next((idx for idx, prefixes in DEX_GROUPS.items()
                         if top in prefixes), 1)
        groups[assigned].append(cf)

    dexes: list[Path] = []
    slot = 1
    for idx in sorted(DEX_GROUPS):
        inputs = [str(p) for p in groups[idx]]
        if not inputs:
            continue
        out = base / f"dex{idx}"
        out.mkdir(parents=True, exist_ok=True)
        run([JAVA, "-cp", str(D8_JAR), "com.android.tools.r8.D8",
             "--lib", str(ANDROID_JAR), "--lib", str(all_jar),
             "--min-api", "21", "--output", str(out), *inputs])
        produced = sorted(out.glob("classes*.dex"))
        for src_dex in produced:
            target = base / ("classes.dex" if slot == 1 else f"classes{slot}.dex")
            shutil.copyfile(src_dex, target)
            dexes.append(target)
            slot += 1
    return dexes


def build_resources(version: str) -> Path:
    base = ROOT / version
    res = base / "res"
    assets = base / "assets"
    is_v2 = version == "v2"

    write(base / "AndroidManifest.xml",
          MANIFEST.replace("__CODE__", "2" if is_v2 else "1")
                  .replace("__NAME__", "2.0" if is_v2 else "1.0"))

    write(res / "values" / "strings.xml", strings_xml(is_v2))
    write(res / "values" / "colors.xml", COLORS_V2 if is_v2 else COLORS_V1)
    write(res / "values" / "dimens.xml", DIMENS)
    write(res / "values" / "styles.xml", STYLES_V2 if is_v2 else STYLES_V1)
    write(res / "values" / "arrays.xml", ARRAYS_V2 if is_v2 else ARRAYS_V1)
    write(res / "values" / "plurals.xml", PLURALS)
    write(res / "values" / "bools.xml", BOOLS)
    write(res / "values" / "integers.xml", INTEGERS)

    write(res / "layout" / "activity_main.xml", LAYOUT_MAIN_V2 if is_v2 else LAYOUT_MAIN_V1)
    write(res / "layout" / "item_product.xml", LAYOUT_ITEM)
    if not is_v2:
        write(res / "layout" / "fragment_home.xml", LAYOUT_HOME)
    else:
        write(res / "layout" / "activity_search.xml", LAYOUT_SEARCH)

    write(res / "drawable" / "bg_primary.xml", DRAWABLE_V1)
    if is_v2:
        write(res / "drawable" / "bg_accent.xml", DRAWABLE_ACCENT)
    write_bytes(res / "mipmap-xxhdpi" / "ic_launcher.png",
                png_bytes(0x03, 0xDA, 0xC5) if is_v2 else png_bytes(0x62, 0x00, 0xEE))

    # raw: config.json is renamed with identical content in v2
    raw_config_name = "settings.json" if is_v2 else "config.json"
    write(res / "raw" / raw_config_name, RAW_CONFIG)
    if not is_v2:
        write(res / "raw" / "legal_notice.txt", RAW_LEGAL)
    else:
        write(res / "raw" / "help.txt", RAW_HELP)
    write(res / "raw" / "catalog.bin", RAW_CATALOG_V2 if is_v2 else RAW_CATALOG_V1)

    write(res / "raw" / "logo.svg", SVG_LOGO_V2 if is_v2 else SVG_LOGO_V1)

    write(assets / "app-config.json", ASSET_CONFIG_V2 if is_v2 else ASSET_CONFIG_V1)
    write(assets / "nested" / "ui" / "preferences.json", ASSET_PREFS)
    write(assets / "images" / "hero.svg", SVG_HERO_V2 if is_v2 else SVG_HERO_V1)
    write(assets / "images" / ("explore.svg" if is_v2 else "legacy.svg"),
          SVG_EXPLORE if is_v2 else SVG_LEGACY)
    write_sqlite(assets / "databases" / "app.db", version)
    if is_v2:
        write_sqlite(assets / "databases" / "explore.db", version, explore=True)
    if is_v2:
        write(assets / "nested" / "ui" / "new_pref.json", ASSET_NEW_PREFS)
    else:
        write(assets / "web" / "index.html", ASSET_HTML)

    write_bytes(base / "lib" / "arm64-v8a" / "libshop.so",
                so_bytes(100, 9000 if is_v2 else 8200))
    write_bytes(base / "lib" / "x86" / "libshop.so", so_bytes(200, 5300))
    if is_v2:
        write_bytes(base / "lib" / "mips" / "libshop.so", so_bytes(300, 4800))

    # --- scaled resources: one group per business domain ---
    all_domains = domains = [
        "catalog", "cart", "checkout", "user", "social", "media",
        "push", "analytics", "network", "storage", "ui", "helper",
    ]
    if is_v2:
        all_domains = domains + ["explore"]

    write(res / "values" / "strings_extra.xml",
          '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          + "\n".join(f'    <string name="label_{d}">{d.title()}</string>' for d in domains)
          + ("\n" + '    <string name="label_explore">Explore</string>' if is_v2 else "")
          + "\n</resources>\n")
    write(res / "values" / "colors_extra.xml",
          '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          + "\n".join(f'    <color name="tint_{d}">#FF{i:02X}00{i:02X}</color>'
                      for i, d in enumerate(domains))
          + ('    <color name="tint_explore">#FF00BB86</color>\n' if is_v2 else "")
          + "\n</resources>\n")
    write(res / "values" / "dimens_extra.xml",
          '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          + "\n".join(f'    <dimen name="gap_{d}">{4 + i}dp</dimen>'
                      for i, d in enumerate(domains))
          + ('    <dimen name="gap_explore">20dp</dimen>\n' if is_v2 else "")
          + "\n</resources>\n")
    write(res / "values" / "themes.xml",
          '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          '    <style name="CardTheme" parent="android:style/Theme.Material">\n'
          + ("        <item name=\"android:background\">@color/tint_cart</item>\n" if is_v2 else "")
          + '    </style>\n</resources>\n')

    for domain in all_domains:
        marker = "-v2" if is_v2 else "-v1"
        write(res / "layout" / f"item_{domain}.xml",
              '<?xml version="1.0" encoding="utf-8"?>\n'
              '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n'
              '    android:orientation="horizontal" android:padding="8dp">\n'
              f'    <TextView android:id="@+id/{domain}_name" android:text="@string/label_{domain}" />\n'
              f'    <TextView android:id="@+id/{domain}_note" android:text="{domain}{marker}" />\n'
              '</LinearLayout>\n')
        write(res / "drawable" / f"bg_{domain}.xml",
              '<?xml version="1.0" encoding="utf-8"?>\n'
              '<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">\n'
              f'    <solid android:color="@color/tint_{domain}" />\n'
              f'    <corners android:radius="{4 + len(domain)}dp" />\n'
              '</shape>\n')
        write(res / "raw" / f"{domain}_config.json",
              f'{{"module":"{domain}","enabled":true,"note":"{marker}","flags":["a","b","c"]}}\n')
        write(assets / domain / "config.json",
              f'{{"module":"{domain}","version":{2 if is_v2 else 1},"note":"{marker}"}}\n')

    # native ABI variants
    write_bytes(base / "lib" / "arm64-v8a" / "libshop_core.so",
                so_bytes(101, 6100 if is_v2 else 5800))
    write_bytes(base / "lib" / "x86" / "libshop_core.so", so_bytes(201, 4100))
    if not is_v2:
        write_bytes(base / "lib" / "armeabi-v7a" / "libshop.so", so_bytes(301, 3900))
    return base


def package_apk(version: str, dexes: list[Path]) -> Path:
    base = ROOT / version
    apk = base / f"{version}.apk"
    run([str(AAPT), "package", "-f",
         "-M", str(base / "AndroidManifest.xml"),
         "-S", str(base / "res"),
         "-A", str(base / "assets"),
         "-I", str(ANDROID_JAR),
         "-F", str(apk)])
    # added after aapt so they don't interfere with resource compilation
    for extra_dir in ("lib",):
        d = base / extra_dir
        if not d.exists():
            continue
        with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    zf.write(f, str(f.relative_to(base)).replace("\\", "/"))
    with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as zf:
        for dex in dexes:
            zf.write(dex, dex.name)
        # fake signature metadata, always different between versions
        zf.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nBuild: {version}\n")
        zf.writestr("META-INF/CERT.SF", f"Signature-Version: 1.0\nVersion: {version}\n")
    return apk


def write_expected_manifest() -> Path:
    """Export the expected-change manifest so tests and CI avoid hard-coded counts.

    Besides the added/deleted/modified classes and resources, record how many
    bytes larger v2 is than v1 (expected_apk_size_delta). The CI size-regression
    check uses it as the baseline.

    Call this only after both APKs have been built; otherwise the file sizes
    (and therefore the delta) are unavailable. main() calls it after the build
    loop for that reason.
    """
    import json
    apk_v1 = ROOT / "v1" / "v1.apk"
    apk_v2 = ROOT / "v2" / "v2.apk"
    manifest = {
        "classes": {
            "added": sorted(set(EXPECTED_ADDED)),
            "deleted": sorted(set(EXPECTED_DELETED)),
            "modified": sorted(set(EXPECTED_MODIFIED)),
        },
        "resources": {k: sorted(set(v)) for k, v in EXPECTED_RES.items()},
        "dex_files": ["classes.dex", "classes2.dex", "classes3.dex"],
        "class_count": {
            "v1": sum(1 for _, _, _, in_v1, _, _ in CATALOG if in_v1),
            "v2": sum(1 for _, _, _, _, in_v2, _ in CATALOG if in_v2),
        },
    }
    # Compute the delta from the real APK file sizes. If a toolchain update
    # changes artifact sizes slightly, the expected baseline follows
    # automatically and CI does not fail merely because the toolchain changed.
    if apk_v1.is_file() and apk_v2.is_file():
        manifest["expected_apk_size_delta"] = (
            apk_v2.stat().st_size - apk_v1.stat().st_size
        )
        manifest["apk_size_delta_tolerance"] = 512
    path = ROOT / "expected.json"
    write(path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> None:
    if not AAPT.exists() or not D8_JAR.exists() or not ANDROID_JAR.exists():
        raise SystemExit(f"Android SDK toolchain not found under {SDK}")
    ROOT.parent.mkdir(parents=True, exist_ok=True)
    for version in ("v1", "v2"):
        print(f"=== building {version} ===", flush=True)
        _, mapping = build_sources(version)
        dexes = build_dexes(version, ROOT / version / "src")
        build_resources(version)
        apk = package_apk(version, dexes)
        n_dex = sum(1 for d in dexes)
        n_cls = sum(1 for line in mapping.read_text(encoding="utf-8").splitlines()
                    if line.endswith(":") and " -> " in line)
        print(f"  {apk} ({apk.stat().st_size} bytes, {n_dex} dex, {n_cls} mapped classes)")
    # Both APKs exist now, so the manifest can record the real size delta.
    manifest_path = write_expected_manifest()
    print(f"  expected manifest: {manifest_path}")
    print("complex fixtures ready:", ROOT)


if __name__ == "__main__":
    main()
