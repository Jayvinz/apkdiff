'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const JS_ROOT = path.resolve(__dirname, '..');
const CLI = path.join(JS_ROOT, 'packages/cli/dist/cli.js');
const FIXTURES = path.join(__dirname, 'fixtures');
const V1 = 'tests/fixtures/v1/v1.apk';
const V2 = 'tests/fixtures/v2/v2.apk';
const C_V1 = 'tests/fixtures/complex/v1/v1.apk';
const C_V2 = 'tests/fixtures/complex/v2/v2.apk';
const PY_REPORTS = path.resolve(JS_ROOT, '../py/report-complex');

function run(args) {
  return spawnSync(process.execPath, [CLI, ...args], {
    cwd: JS_ROOT,
    encoding: 'utf8',
  });
}

function withTempDir(fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apkdiff-js-'));
  try {
    return fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test('cli: json, html, markdown and console output', () => {
  if (!fs.existsSync(path.join(FIXTURES, 'v1/v1.apk'))) return;
  withTempDir((tmp) => {
    const result = run([V1, V2, '--format', 'json,html,markdown,console', '-o', tmp]);
    assert.equal(result.status, 0, result.stderr);
    const data = JSON.parse(fs.readFileSync(path.join(tmp, 'apkdiff.json'), 'utf8'));
    assert.equal(data.summary.class_added, 1);
    assert.equal(data.summary.class_deleted, 1);
    assert.equal(data.summary.class_modified, 1);
    const html = fs.readFileSync(path.join(tmp, 'apkdiff.html'), 'utf8');
    assert.ok(html.includes('com.example.Alpha'));
    assert.ok(html.includes('APK Diff Report'));
    assert.ok(fs.existsSync(path.join(tmp, 'apkdiff.md')));
    assert.ok(result.stdout.includes('APK DIFF REPORT'));
  });
});

test('cli: --fail-on-regression returns 1 when the new APK is larger', () => {
  if (!fs.existsSync(path.join(FIXTURES, 'complex/v1/v1.apk'))) return;
  withTempDir((tmp) => {
    const result = run([C_V1, C_V2, '--format', 'json', '--fail-on-regression', '-o', tmp]);
    assert.equal(result.status, 1);
  });
});

test('cli: missing APK is an error', () => {
  const result = run(['does-not-exist.apk', 'also-missing.apk']);
  assert.equal(result.status, 2);
  assert.ok(result.stderr.includes('APK 不存在'));
});

test('cli: --help exits zero', () => {
  const result = run(['--help']);
  assert.equal(result.status, 0);
  assert.ok(result.stdout.includes('usage: apkdiff'));
});

test('cli: invalid --format is rejected', () => {
  const result = run([V1, V2, '--format', 'xml']);
  assert.equal(result.status, 2);
  assert.ok(result.stderr.includes('不支持的输出格式'));
});

test('cli: reports are byte-identical to the Python implementation', () => {
  if (!fs.existsSync(path.join(FIXTURES, 'complex/v1/v1.apk'))) return;
  const pythonReports = ['apkdiff.json', 'apkdiff.html', 'apkdiff.md'];
  if (pythonReports.some((name) => !fs.existsSync(path.join(PY_REPORTS, name)))) {
    return;
  }
  withTempDir((tmp) => {
    const result = run([
      C_V1, C_V2, '--detect-renames', '--format', 'json,html,markdown', '-o', tmp,
    ]);
    assert.equal(result.status, 0, result.stderr);
    for (const name of pythonReports) {
      const expected = fs.readFileSync(path.join(PY_REPORTS, name), 'utf8');
      const actual = fs.readFileSync(path.join(tmp, name), 'utf8');
      assert.equal(actual, expected, `${name} differs from the Python report`);
    }
  });
});
