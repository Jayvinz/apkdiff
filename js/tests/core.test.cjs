'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const core = require('@jayvinz/apkdiff-core');

const FIXTURES = path.join(__dirname, 'fixtures');
const V1 = path.join(FIXTURES, 'v1/v1.apk');
const V2 = path.join(FIXTURES, 'v2/v2.apk');
const COMPLEX = path.join(FIXTURES, 'complex');
const C_V1 = path.join(COMPLEX, 'v1/v1.apk');
const C_V2 = path.join(COMPLEX, 'v2/v2.apk');
const C_MANIFEST = path.join(COMPLEX, 'expected.json');

function analyze(apk) {
  const mappingPath = path.join(path.dirname(apk), 'mapping.txt');
  const mapping = fs.existsSync(mappingPath) ? core.Mapping.parse(mappingPath) : null;
  return core.analyzeApk(apk, mapping);
}

function analyzeComplex(apk) {
  return core.analyzeApk(apk, core.Mapping.parse(path.join(path.dirname(apk), 'mapping.txt')));
}

function statuses(changes) {
  return Object.fromEntries(changes.map((change) => [change.key, change.status]));
}

function skipIfMissing(t, files) {
  if (files.some((file) => !fs.existsSync(file))) {
    t.skip('fixtures missing');
    return true;
  }
  return false;
}

test('small fixture: class changes', (t) => {
  if (skipIfMissing(t, [V1, V2])) return;
  const result = core.diffApks(analyze(V1), analyze(V2));
  assert.deepStrictEqual(statuses(result.classes), {
    'com.example.Alpha': core.MODIFIED,
    'com.example.Gamma': core.DELETED,
    'com.example.Delta': core.ADDED,
  });
});

test('small fixture: resource changes', (t) => {
  if (skipIfMissing(t, [V1, V2])) return;
  const result = core.diffApks(analyze(V1), analyze(V2));
  const status = statuses(result.resources);
  assert.equal(status['res/raw/extra.txt'], core.ADDED);
  assert.equal(status['assets/config.json'], core.MODIFIED);
  assert.equal(status['resources.arsc'], core.MODIFIED);
});

test('small fixture: identical APKs have no changes', (t) => {
  if (skipIfMissing(t, [V1])) return;
  const analysis = analyze(V1);
  const result = core.diffApks(analysis, analysis);
  assert.deepStrictEqual(result.classes, []);
  assert.deepStrictEqual(result.resources, []);
});

test('small fixture: dex bytes are fully accounted', (t) => {
  if (skipIfMissing(t, [V1, V2])) return;
  for (const apk of [V1, V2]) {
    const analysis = analyze(apk);
    const dexTotal = analysis.dexFiles.reduce((sum, dex) => sum + dex.fileSize, 0);
    assert.equal(dexTotal, analysis.totalClassBytes() + analysis.unattributedDexBytes());
  }
});

test('small fixture: mapping deobfuscation', (t) => {
  if (skipIfMissing(t, [V1])) return;
  const analysis = analyze(V1);
  assert.ok(analysis.classes.has('com.example.Alpha'));
  assert.ok(!analysis.classes.has('p.a'));
});

test('complex fixture: multidex and no parse warnings', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2, C_MANIFEST])) return;
  const expected = JSON.parse(fs.readFileSync(C_MANIFEST, 'utf8'));
  for (const apk of [C_V1, C_V2]) {
    const analysis = analyzeComplex(apk);
    assert.deepStrictEqual(
      analysis.dexFiles.map((dex) => dex.path),
      expected.dex_files,
    );
    assert.deepStrictEqual(analysis.warnings, []);
    for (const [name, cls] of analysis.classes) {
      assert.equal(cls.warning, '', `${name}: ${cls.warning}`);
      assert.equal(cls.partial, false, `${name}: partial parse`);
    }
    const dexTotal = analysis.dexFiles.reduce((sum, dex) => sum + dex.fileSize, 0);
    assert.equal(dexTotal, analysis.totalClassBytes() + analysis.unattributedDexBytes());
  }
});

test('complex fixture: business class changes match manifest', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2, C_MANIFEST])) return;
  const expected = JSON.parse(fs.readFileSync(C_MANIFEST, 'utf8'));
  const result = core.diffApks(analyzeComplex(C_V1), analyzeComplex(C_V2));
  const status = statuses(result.classes);
  for (const [state, label] of [
    [core.ADDED, 'added'], [core.DELETED, 'deleted'], [core.MODIFIED, 'modified'],
  ]) {
    const actual = new Set(
      Object.entries(status)
        .filter(([name, value]) => name.startsWith('com.shop.') && value === state)
        .map(([name]) => name),
    );
    assert.deepStrictEqual(actual, new Set(expected.classes[label]));
  }
  // A large set of unrelated classes stays unchanged even though the DEX index pools
  // were reshuffled by the added/removed classes.
  assert.ok(!status['com.shop.ui.ProductListActivity']);
  assert.ok(!status['com.shop.ui.ProductDetailActivity']);
  assert.ok(!status['com.shop.util.Logger']);
});

test('complex fixture: synthetic and inner classes are present', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2])) return;
  const analysis = analyzeComplex(C_V1);
  const synthetic = [...analysis.classes.keys()].filter((name) => name.includes('$'));
  assert.ok(synthetic.length > 10, 'inner/synthetic classes missing or too few');
  const result = core.diffApks(analyzeComplex(C_V1), analyzeComplex(C_V2));
  assert.ok(result.classes.some((change) => change.key.includes('$') && change.status === core.ADDED));
  assert.ok(result.classes.some((change) => change.key.includes('$') && change.status === core.DELETED));
});

test('complex fixture: resource changes match manifest', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2, C_MANIFEST])) return;
  const expected = JSON.parse(fs.readFileSync(C_MANIFEST, 'utf8'));
  const result = core.diffApks(analyzeComplex(C_V1), analyzeComplex(C_V2), false, true);
  const status = statuses(result.resources);
  for (const [state, label] of [
    [core.ADDED, 'added'], [core.DELETED, 'deleted'],
    [core.MODIFIED, 'modified'], [core.RENAMED, 'renamed'],
  ]) {
    const actual = new Set(
      Object.entries(status).filter(([, value]) => value === state).map(([name]) => name),
    );
    assert.deepStrictEqual(actual, new Set(expected.resources[label]));
  }
  assert.ok(!status['res/raw/config.json']);
});

test('complex fixture: resource types are covered', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2])) return;
  const analysis = analyzeComplex(C_V1);
  const names = [...analysis.entries.keys()];
  for (const suffix of ['.xml', '.png', '.svg', '.db', '.so', '.json', '.bin']) {
    assert.ok(names.some((name) => name.endsWith(suffix)), `fixture has no ${suffix} entry`);
  }
  for (const prefix of ['res/', 'assets/', 'lib/']) {
    assert.ok(names.some((name) => name.startsWith(prefix)), prefix);
  }
  assert.ok(names.includes('resources.arsc'));

  const result = core.diffApks(
    analyzeComplex(C_V1), analyzeComplex(C_V2), false, true);
  const status = statuses(result.resources);
  assert.equal(status['assets/databases/app.db'], core.MODIFIED);
  assert.equal(status['assets/databases/explore.db'], core.ADDED);
  assert.equal(status['assets/images/hero.svg'], core.MODIFIED);
  assert.equal(status['assets/images/explore.svg'], core.ADDED);
  assert.equal(status['assets/images/legacy.svg'], core.DELETED);
  assert.equal(status['res/raw/logo.svg'], core.MODIFIED);
  assert.equal(status['res/mipmap-xxhdpi-v4/ic_launcher.png'], core.MODIFIED);
});

test('complex fixture: META-INF is opt-in', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2])) return;
  const oldAnalysis = analyzeComplex(C_V1);
  const newAnalysis = analyzeComplex(C_V2);
  const defaultResult = core.diffApks(oldAnalysis, newAnalysis);
  assert.ok(!defaultResult.resources.some((change) => change.key.startsWith('META-INF')));
  const withMeta = core.diffApks(oldAnalysis, newAnalysis, true, false);
  const meta = statuses(withMeta.resources.filter((change) => change.key.startsWith('META-INF')));
  assert.equal(meta['META-INF/MANIFEST.MF'], core.MODIFIED);
  assert.equal(meta['META-INF/CERT.SF'], core.MODIFIED);
});

test('complex fixture: business class counts match manifest', (t) => {
  if (skipIfMissing(t, [C_V1, C_V2, C_MANIFEST])) return;
  const expected = JSON.parse(fs.readFileSync(C_MANIFEST, 'utf8'));
  const v1 = [...analyzeComplex(C_V1).classes.keys()]
    .filter((name) => name.startsWith('com.shop.')).length;
  const v2 = [...analyzeComplex(C_V2).classes.keys()]
    .filter((name) => name.startsWith('com.shop.')).length;
  assert.equal(v1, expected.class_count.v1);
  assert.equal(v2, expected.class_count.v2);
});

test('helpers: uleb128', () => {
  assert.deepStrictEqual(core.uleb128(Buffer.from([0]), 0), [0, 1]);
  assert.deepStrictEqual(core.uleb128(Buffer.from([0x81, 0x80, 0x04]), 0), [65537, 3]);
});

test('helpers: mapping parse', (t) => {
  if (skipIfMissing(t, [path.join(FIXTURES, 'v1/mapping.txt')])) return;
  const mapping = core.Mapping.parse(path.join(FIXTURES, 'v1/mapping.txt'));
  assert.equal(mapping.originalName('p.a'), 'com.example.Alpha');
  assert.equal(mapping.deobfuscateDescriptor('Lp/b;'), 'com.example.Beta');
  assert.equal(mapping.originalName('unknown.X'), 'unknown.X');
});

test('helpers: categorize', () => {
  assert.equal(core.categorize('classes2.dex'), 'dex');
  assert.equal(core.categorize('res/drawable/icon.png'), 'res');
  assert.equal(core.categorize('assets/data.json'), 'assets');
  assert.equal(core.categorize('lib/arm64-v8a/libx.so'), 'lib');
  assert.equal(core.categorize('META-INF/CERT.RSA'), 'meta');
  assert.equal(core.categorize('resources.arsc'), 'resources');
});

test('helpers: empty mapping is harmless', () => {
  const mapping = core.loadMapping(null);
  assert.equal(mapping.originalName('any.Class'), 'any.Class');
  assert.equal(mapping.classNames.get('any.Class'), undefined);
});

test('reports: human size formatting', () => {
  assert.equal(core.humanSize(257), '0.25 KB');
  assert.equal(core.humanSize(7685), '7.50 KB');
  assert.equal(core.humanDelta(7685), '+7.50 KB');
  assert.equal(core.humanDelta(-256), '-0.25 KB');
});
