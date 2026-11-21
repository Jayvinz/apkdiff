"""Automated unit and end-to-end tests.

Run (install both local packages first):
    pip install -e packages/core -e packages/cli
    python -m unittest discover -s tests -v

The fixture APKs are generated with the real Android toolchain (javac -> d8 ->
aapt), not hand-made; see make_fixtures.py and make_complex_fixture.py.

Groups:
    TestDiff / TestHelpers        small fixture, quick smoke tests
    TestComplexFixture            complex fixture (200+ classes, 3 dex files),
                                  expected changes read from expected.json

Tests skip automatically when fixtures are missing. CI must run the two
make_*.py scripts before the tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apkdiff_core.apk import analyze_apk, categorize
from apkdiff_core.dex import _uleb128
from apkdiff_core.diff import ADDED, DELETED, MODIFIED, diff_apks
from apkdiff_core.mapping import Mapping

ROOT = Path(__file__).resolve().parent / "fixtures"
V1 = ROOT / "v1" / "v1.apk"
V2 = ROOT / "v2" / "v2.apk"


@unittest.skipUnless(V1.exists() and V2.exists(), "run tests/make_fixtures.py first")
class TestDiff(unittest.TestCase):
    def analyze(self, apk: Path):
        mapping_path = apk.parent / "mapping.txt"
        mapping = Mapping.parse(str(mapping_path)) if mapping_path.exists() else None
        return analyze_apk(str(apk), mapping)

    def test_class_changes(self):
        result = diff_apks(self.analyze(V1), self.analyze(V2))
        statuses = {c.key: c.status for c in result.classes}
        self.assertEqual(statuses, {
            "com.example.Alpha": MODIFIED,
            "com.example.Gamma": DELETED,
            "com.example.Delta": ADDED,
        }, statuses)

    def test_resource_changes(self):
        result = diff_apks(self.analyze(V1), self.analyze(V2))
        statuses = {c.key: c.status for c in result.resources}
        self.assertEqual(statuses.get("res/raw/extra.txt"), ADDED)
        self.assertEqual(statuses.get("assets/config.json"), MODIFIED)
        self.assertEqual(statuses.get("resources.arsc"), MODIFIED)

    def test_identical_apks_have_no_changes(self):
        a = self.analyze(V1)
        result = diff_apks(a, a)
        self.assertEqual(result.classes, [])
        self.assertEqual(result.resources, [])

    def test_dex_bytes_accounted(self):
        for apk in (V1, V2):
            with self.subTest(apk=apk):
                a = self.analyze(apk)
                dex_total = sum(d.file_size for d in a.dex_files)
                self.assertEqual(a.total_class_bytes + a.unattributed_dex_bytes, dex_total)

    def test_mapping_deobfuscation(self):
        a = self.analyze(V1)
        self.assertIn("com.example.Alpha", a.classes)
        self.assertNotIn("p.a", a.classes)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-m", "apkdiff", str(V1), str(V2),
                 "--format", "json,html,markdown,console", "-o", tmp],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads((Path(tmp) / "apkdiff.json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["class_added"], 1)
            self.assertEqual(data["summary"]["class_deleted"], 1)
            self.assertEqual(data["summary"]["class_modified"], 1)
            html_text = (Path(tmp) / "apkdiff.html").read_text(encoding="utf-8")
            self.assertIn("com.example.Alpha", html_text)
            self.assertIn("APK Diff Report", html_text)
            self.assertTrue((Path(tmp) / "apkdiff.md").exists())


C_BASE = ROOT / "complex"
C_V1 = C_BASE / "v1" / "v1.apk"
C_V2 = C_BASE / "v2" / "v2.apk"
C_MANIFEST = C_BASE / "expected.json"


@unittest.skipUnless(C_V1.exists() and C_V2.exists() and C_MANIFEST.exists(),
                     "run tests/make_complex_fixture.py first")
class TestComplexFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exp = json.loads(C_MANIFEST.read_text(encoding="utf-8"))

    def analyze(self, apk: Path):
        return analyze_apk(str(apk), Mapping.parse(str(apk.parent / "mapping.txt")))

    def test_multidex_and_no_parse_warnings(self):
        for apk in (C_V1, C_V2):
            with self.subTest(apk=apk):
                a = self.analyze(apk)
                self.assertEqual([d.path for d in a.dex_files],
                                 self.exp["dex_files"])
                self.assertEqual(a.warnings, [])
                # No individual class may carry a parser warning either.
                for name, cls in a.classes.items():
                    self.assertEqual(cls.warning, "", f"{name}: {cls.warning}")
                    self.assertFalse(cls.partial, f"{name}: partial parse")
                self.assertEqual(a.total_class_bytes + a.unattributed_dex_bytes,
                                 sum(d.file_size for d in a.dex_files))

    def test_business_class_changes_match_manifest(self):
        result = diff_apks(self.analyze(C_V1), self.analyze(C_V2))
        statuses = {c.key: c.status for c in result.classes
                    if c.key.startswith("com.shop.")}
        for status, label in ((ADDED, "added"), (DELETED, "deleted"),
                              (MODIFIED, "modified")):
            with self.subTest(status=label):
                expected = set(self.exp["classes"][label])
                actual = {k for k, v in statuses.items() if v == status}
                self.assertEqual(actual, expected)
        # A large set of unrelated classes stays unchanged even though the
        # DEX index pools were reshuffled by the added/removed classes.
        self.assertNotIn("com.shop.ui.ProductListActivity", statuses)
        self.assertNotIn("com.shop.ui.ProductDetailActivity", statuses)
        self.assertNotIn("com.shop.util.Logger", statuses)  # annotation parse regression

    def test_synthetic_and_inner_classes_are_present(self):
        a = self.analyze(C_V1)
        synthetic = [k for k in a.classes if "$" in k]
        self.assertGreater(len(synthetic), 10,
                           "inner/synthetic classes missing or too few")
        result = diff_apks(self.analyze(C_V1), self.analyze(C_V2))
        changed = [c.key for c in result.classes if "$" in c.key]
        self.assertTrue(any(c.status == ADDED for c in result.classes
                            if "$" in c.key))
        self.assertTrue(any(c.status == DELETED for c in result.classes
                            if "$" in c.key))
        self.assertTrue(changed)

    def test_resource_changes_match_manifest(self):
        result = diff_apks(self.analyze(C_V1), self.analyze(C_V2),
                           detect_renames=True)
        statuses = {c.key: c.status for c in result.resources}
        for status, label in ((ADDED, "added"), (DELETED, "deleted"),
                              (MODIFIED, "modified"),
                              ("renamed", "renamed")):
            with self.subTest(status=label):
                expected = set(self.exp["resources"][label])
                actual = {k for k, v in statuses.items() if v == status}
                self.assertEqual(actual, expected)
        self.assertNotIn("res/raw/config.json", statuses)

    def test_resource_types_are_covered(self):
        """XML, PNG, SVG, assets DB and native libs are inventoried and diffed."""
        analysis = self.analyze(C_V1)
        names = set(analysis.entries)
        for suffix in (".xml", ".png", ".svg", ".db", ".so", ".json", ".bin"):
            self.assertTrue(
                any(name.endswith(suffix) for name in names),
                f"fixture has no {suffix} entry",
            )
        for prefix in ("res/", "assets/", "lib/"):
            self.assertTrue(any(name.startswith(prefix) for name in names), prefix)
        self.assertIn("resources.arsc", names)

        result = diff_apks(self.analyze(C_V1), self.analyze(C_V2), detect_renames=True)
        statuses = {change.key: change.status for change in result.resources}
        self.assertEqual(statuses["assets/databases/app.db"], MODIFIED)
        self.assertEqual(statuses["assets/databases/explore.db"], ADDED)
        self.assertEqual(statuses["assets/images/hero.svg"], MODIFIED)
        self.assertEqual(statuses["assets/images/explore.svg"], ADDED)
        self.assertEqual(statuses["assets/images/legacy.svg"], DELETED)
        self.assertEqual(statuses["res/raw/logo.svg"], MODIFIED)
        self.assertEqual(statuses["res/mipmap-xxhdpi-v4/ic_launcher.png"], MODIFIED)

    def test_meta_files_are_opt_in(self):
        old, new = self.analyze(C_V1), self.analyze(C_V2)
        default = diff_apks(old, new)
        self.assertFalse(any(c.key.startswith("META-INF") for c in default.resources))
        with_meta = diff_apks(old, new, include_meta=True)
        meta = {c.key: c.status for c in with_meta.resources
                if c.key.startswith("META-INF")}
        self.assertEqual(meta.get("META-INF/MANIFEST.MF"), MODIFIED)
        self.assertEqual(meta.get("META-INF/CERT.SF"), MODIFIED)


class TestHelpers(unittest.TestCase):
    def test_uleb128(self):
        self.assertEqual(_uleb128(b"\x00", 0), (0, 1))
        self.assertEqual(_uleb128(b"\x81\x80\x04", 0), (65537, 3))

    def test_mapping_parse(self):
        path = ROOT / "v1" / "mapping.txt"
        m = Mapping.parse(str(path))
        self.assertEqual(m.original_name("p.a"), "com.example.Alpha")
        self.assertEqual(m.deobfuscate_descriptor("Lp/b;"), "com.example.Beta")
        self.assertEqual(m.original_name("unknown.X"), "unknown.X")

    def test_categorize(self):
        self.assertEqual(categorize("classes2.dex"), "dex")
        self.assertEqual(categorize("res/drawable/icon.png"), "res")
        self.assertEqual(categorize("assets/data.json"), "assets")
        self.assertEqual(categorize("lib/arm64-v8a/libx.so"), "lib")
        self.assertEqual(categorize("META-INF/CERT.RSA"), "meta")
        self.assertEqual(categorize("resources.arsc"), "resources")


if __name__ == "__main__":
    unittest.main()
