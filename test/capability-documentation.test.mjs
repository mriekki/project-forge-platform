import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('published optional Kits remain separate from the default profile and runtime activation', async () => {
  const metadata = JSON.parse(await source('assets/components.json'));
  const optional = ['authentication', 'feedback', 'release-notes'];
  assert.deepEqual(metadata.profiles[metadata.defaultProfile].components, ['core', 'deployment']);
  for (const kit of optional) {
    assert.ok(metadata.components[kit], `Package must expose exact ${kit} source provenance`);
    assert.ok(!metadata.profiles[metadata.defaultProfile].components.includes(kit),
      `Default profile must not activate optional ${kit}`);
    assert.ok(Object.values(metadata.profiles).some(profile => profile.components.includes(kit)),
      `No explicit package profile selects ${kit}`);
  }
  for (const [name, profile] of Object.entries(metadata.profiles)) {
    if (profile.components.includes('release-notes')) {
      assert.ok(name.includes('release-notes'), 'Release Notes are only included by explicit profiles');
    }
  }
});

test('public README and Welcome do not conflate package, Project integration, or Production state', async () => {
  const readme = await source('README.md');
  const welcome = await source('WELCOME.md');
  const design = await source('docs/system/PROJECT_FORGE_SYSTEM_DESIGN.md');
  for (const feature of ['Authentication', 'GitHub Issues Feedback', 'Release Notes']) {
    assert.match(readme, new RegExp(feature.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.match(readme, /project-forge enable feedback/);
  assert.match(readme, /project-forge enable release-notes/);
  assert.match(readme, /package inclusion alone|publishing the umbrella package does not/i);
  assert.match(welcome, /Start from an idea/);
  assert.match(welcome, /Start from an existing product or source/);
  assert.match(welcome, /Adopt an existing repository/);
  assert.match(design, /project-forge-auth-kit/);
  assert.match(design, /project-forge-feedback-kit/);
  assert.match(design, /project-forge-release-notes-kit/);
});

test('passkey packaging marker cannot silently enable candidate support', async () => {
  const marker = JSON.parse(await source('assets/generated/authentication/docs/PASSKEY_SUPPORT.json'));
  const authSupportDoc = await source('README.md');
  assert.equal(marker.enabledByDefault, false);
  assert.ok(['candidate', 'qualified'].includes(marker.supportState));
  assert.equal(marker.googleRecovery, true);
  if (marker.supportState === 'candidate') {
    assert.match(authSupportDoc, /passkey support may still be a \*\*candidate\*\*/i);
  }
});

test('Release Notes opt-in documentation remains default off and runtime-gated', async () => {
  const contract = await source('assets/generated/release-notes/docs/PROJECT_INTEGRATION.md');
  assert.match(contract, /default OFF/i);
  assert.match(contract, /Production activation/i);
  assert.match(contract, /does \*\*not\*\* qualify a new generated Project/);
});
