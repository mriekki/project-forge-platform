import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { run } from '../src/cli.mjs';
import { applyProfile, checkProfile, planProfile } from '../src/engine.mjs';
import { parseArgs, reconcileReleaseNotesProfiles } from '../scripts/prepare-package-update.mjs';

const BASES = {
  'greenfield-project': ['core', 'deployment'],
  'greenfield-household-project': ['core', 'deployment', 'authentication'],
  'greenfield-feedback-project': ['core', 'deployment', 'feedback'],
  'greenfield-household-feedback-project': ['core', 'deployment', 'authentication', 'feedback']
};

function fixture(includeKit = true) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pf-release-notes-'));
  const consumer = path.join(root, 'consumer');
  const sourceRoot = path.join(root, 'package');
  fs.mkdirSync(consumer, { recursive: true });
  const ids = ['core', 'deployment', 'authentication', 'feedback',
    ...(includeKit ? ['release-notes'] : [])];
  const components = {};
  for (const [i, id] of ids.entries()) {
    const assetDir = path.join(sourceRoot, 'assets', 'generated', id);
    const descriptorDir = path.join(sourceRoot, 'assets', id);
    fs.mkdirSync(assetDir, { recursive: true });
    fs.mkdirSync(descriptorDir, { recursive: true });
    fs.writeFileSync(path.join(assetDir, id + '.txt'), id + ' source\n');
    fs.writeFileSync(path.join(descriptorDir, 'distribution.json'),
      JSON.stringify({ mappings: [{ source: id + '.txt', destination: 'tools/' + id + '.txt' }] }));
    components[id] = {
      revision: (i + 10).toString(16).repeat(40),
      distribution: id === 'core' ? 'greenfield-workspace' : 'greenfield-project',
      descriptor: 'assets/' + id + '/distribution.json',
      sourceRoot: 'assets/generated/' + id,
      ...(id === 'core' ? { version: '4.5.1' } : {})
    };
  }
  const profiles = Object.fromEntries(Object.entries(BASES)
    .map(([name, components]) => [name, { components: [...components] }]));
  if (includeKit) reconcileReleaseNotesProfiles(profiles);
  return {
    root, consumer,
    data: {
      root: sourceRoot, pkg: { name: '@mriekki/project-forge', version: '4.33.0' },
      assets: { defaultProfile: 'greenfield-project', profiles, components }
    }
  };
}

test('default profile stays unchanged; four optional profiles are deterministic and idempotent', () => {
  const profiles = Object.fromEntries(Object.entries(BASES)
    .map(([name, components]) => [name, { components: [...components] }]));
  const untouched = structuredClone(profiles);
  reconcileReleaseNotesProfiles(profiles);
  assert.equal(Object.keys(profiles).length, 8);
  for (const [name, components] of Object.entries(BASES)) {
    assert.deepEqual(profiles[name], untouched[name]);
    const target = name.replace(/-project$/, '-release-notes-project');
    assert.deepEqual(profiles[target].components, [...components, 'release-notes']);
  }
  reconcileReleaseNotesProfiles(profiles);
  profiles['greenfield-feedback-release-notes-project'].components.pop();
  assert.throws(() => reconcileReleaseNotesProfiles(profiles), /differs from its approved base/);
});

test('unreviewed source components and stale preparation parameters fail closed', () => {
  const profiles = { 'greenfield-project': { components: ['core', 'deployment', 'feedback'] } };
  assert.throws(() => reconcileReleaseNotesProfiles(profiles), /unexpected components/);
  const args = parseArgs(['--version', '4.33.0', '--core-root', '/tmp/core',
    '--deployment-root', '/tmp/deploy', '--release-notes-root', '/tmp/kit']);
  assert.equal(args.releaseNotesRoot, '/tmp/kit');
  assert.throws(() => parseArgs(['--version', '4.33.0', '--release-notes-root', '/tmp/kit']),
    /core-root, and --deployment-root are required/);
});

test('explicit Release Notes opt-in preserves Auth, Feedback and existing component bytes', async () => {
  const f = fixture();
  try {
    const base = 'greenfield-household-feedback-project';
    applyProfile(f.data, planProfile(f.data, base, f.consumer), f.consumer, 'fmp', 'approved');
    const old = Object.fromEntries(BASES[base].map(id =>
      [id, fs.readFileSync(path.join(f.consumer, 'tools', id + '.txt'))]));
    assert.equal(await run(['enable', 'release-notes', '--root', f.consumer], f.data), 0);
    assert.equal(fs.existsSync(path.join(f.consumer, 'RELEASE_NOTES_BASELINE.json')), false);
    assert.equal(await run(['enable', 'release-notes', '--root', f.consumer, '--apply'], f.data), 0);
    const umbrella = JSON.parse(fs.readFileSync(path.join(f.consumer, 'PROJECT_FORGE_BASELINE.json')));
    assert.equal(umbrella.profile, 'greenfield-household-feedback-release-notes-project');
    assert.equal(umbrella.consumerBaseline, 'approved');
    assert.deepEqual(Object.keys(umbrella.components).sort(),
      ['authentication', 'core', 'deployment', 'feedback', 'release-notes']);
    assert.equal(fs.readFileSync(path.join(f.consumer, 'tools/release-notes.txt'), 'utf8'), 'release-notes source\n');
    for (const [id, bytes] of Object.entries(old)) {
      assert.deepEqual(fs.readFileSync(path.join(f.consumer, 'tools', id + '.txt')), bytes);
    }
    assert.equal(checkProfile(f.data, umbrella.profile, f.consumer).clean, true);
  } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
});

test('missing Kit and modified managed files cannot force Release Notes opt-in', async () => {
  for (const includeKit of [false, true]) {
    const f = fixture(includeKit);
    try {
      applyProfile(f.data, planProfile(f.data, 'greenfield-project', f.consumer),
        f.consumer, 'fmp', 'approved');
      const before = fs.readFileSync(path.join(f.consumer, 'PROJECT_FORGE_BASELINE.json'));
      if (includeKit) {
        fs.writeFileSync(path.join(f.consumer, 'tools/core.txt'), 'unreviewed edit\n');
        assert.equal(await run(['enable', 'release-notes', '--root', f.consumer, '--apply'], f.data), 2);
      } else {
        await assert.rejects(run(['enable', 'release-notes', '--root', f.consumer, '--apply'], f.data),
          /does not provide qualified Release Notes/);
      }
      assert.equal(fs.existsSync(path.join(f.consumer, 'tools/release-notes.txt')), false);
      assert.deepEqual(fs.readFileSync(path.join(f.consumer, 'PROJECT_FORGE_BASELINE.json')), before);
    } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
  }
});

test('Feedback can be enabled after Release Notes without losing independent Kit baseline', async () => {
  const f = fixture();
  try {
    applyProfile(f.data, planProfile(f.data, 'greenfield-household-project', f.consumer),
      f.consumer, 'fmp', 'approved');
    assert.equal(await run(['enable', 'release-notes', '--root', f.consumer, '--apply'], f.data), 0);
    assert.equal(await run(['enable', 'feedback', '--root', f.consumer, '--apply'], f.data), 0);
    const umbrella = JSON.parse(fs.readFileSync(path.join(f.consumer, 'PROJECT_FORGE_BASELINE.json')));
    assert.equal(umbrella.profile, 'greenfield-household-feedback-release-notes-project');
    assert.ok(checkProfile(f.data, umbrella.profile, f.consumer).clean);
    assert.ok(fs.existsSync(path.join(f.consumer, 'RELEASE_NOTES_BASELINE.json')));
  } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
});

test('new Project default installation does not install optional Release Notes files', () => {
  const f = fixture();
  try {
    applyProfile(f.data, planProfile(f.data, 'greenfield-project', f.consumer), f.consumer, 'fresh', 'v1');
    assert.equal(fs.existsSync(path.join(f.consumer, 'RELEASE_NOTES_BASELINE.json')), false);
    assert.equal(fs.existsSync(path.join(f.consumer, 'tools/release-notes.txt')), false);
    const baseline = JSON.parse(fs.readFileSync(path.join(f.consumer, 'PROJECT_FORGE_BASELINE.json')));
    assert.deepEqual(Object.keys(baseline.components), ['core', 'deployment']);
  } finally { fs.rmSync(f.root, { recursive: true, force: true }); }
});


test('Release Notes preparation and publication verify accepted exact private source', () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const prepare = fs.readFileSync(path.join(root, '.github/workflows/prepare-package-release.yml'), 'utf8');
  const publish = fs.readFileSync(path.join(root, '.github/workflows/npm-publish.yml'), 'utf8');
  const tarball = fs.readFileSync(path.join(root, 'scripts/prepare-release.mjs'), 'utf8');
  const assembly = fs.readFileSync(path.join(root, 'scripts/assemble-assets.mjs'), 'utf8');

  assert.match(prepare, /release_notes_revision:/);
  assert.match(prepare, /RELEASE_NOTES_SOURCE_REPOSITORY/);
  assert.match(prepare, /PROJECT_FORGE_RELEASE_NOTES_SOURCE_REPOSITORY/);
  assert.match(prepare, /verify_checkout \.release-sources\/release-notes "\$RELEASE_NOTES_REVISION"/);
  assert.match(prepare, /--release-notes-root \.release-sources\/release-notes/);
  assert.match(prepare, /No successful accepted Release Notes Kit main CI for exact revision/);
  assert.match(prepare, /run\.status === 'completed' && run\.conclusion === 'success'/);
  assert.match(prepare, /'assets\/release-notes\/distribution.json'/);
  assert.match(prepare, /git add assets\/release-notes\/distribution.json/);

  assert.match(publish, /ids\.includes\('release-notes'\)/);
  assert.match(publish, /RELEASE_NOTES_SOURCE_REPOSITORY/);
  assert.match(publish, /steps\.pins\.outputs\.release_notes/);
  assert.match(publish, /ref: \$\{\{ steps\.pins\.outputs\.release_notes \}\}/);
  assert.match(publish, /verify_checkout \.release-sources\/release-notes "\$RELEASE_NOTES_REVISION"/);
  assert.match(publish, /--release-notes-root \.release-sources\/release-notes/);
  assert.match(publish, /No successful accepted Release Notes Kit main CI for exact publication revision/);
  assert.match(publish, /steps\.pins\.outputs\.release_notes/);
  assert.match(publish, /'release-notes': \{ revision: components\.components\['release-notes'\]\.revision \}/);
  assert.match(tarball, /--release-notes-root/);
  assert.match(assembly, /--release-notes-root/);

  // Source checkout and exact commit checks precede package preparation.
  assert.ok(prepare.indexOf('Verify exact component main revisions') <
    prepare.indexOf('Prepare deterministic package metadata and descriptors'));
  assert.ok(publish.indexOf('Verify exact private source checkouts') <
    publish.indexOf('Prepare reproducible release candidate'));
});
