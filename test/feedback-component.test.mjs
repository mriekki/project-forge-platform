import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { applyProfile, checkProfile, planProfile } from '../src/engine.mjs';
import { reconcileFeedbackProfiles, reconcileHouseholdAuthProfile } from '../scripts/prepare-package-update.mjs';

test('Feedback profiles are opt-in and retain independent Auth selection', () => {
  const profiles = { 'greenfield-project': { components: ['core', 'deployment'] } };
  reconcileHouseholdAuthProfile(profiles);
  reconcileFeedbackProfiles(profiles);
  assert.deepEqual(profiles['greenfield-project'].components, ['core', 'deployment']);
  assert.deepEqual(profiles['greenfield-household-project'].components, ['core', 'deployment', 'authentication']);
  assert.deepEqual(profiles['greenfield-feedback-project'].components, ['core', 'deployment', 'feedback']);
  assert.deepEqual(profiles['greenfield-household-feedback-project'].components, ['core', 'deployment', 'authentication', 'feedback']);
  const original = structuredClone(profiles);
  reconcileFeedbackProfiles(profiles);
  assert.deepEqual(profiles, original);
  profiles['greenfield-feedback-project'].components.push('authentication');
  assert.throws(() => reconcileFeedbackProfiles(profiles), /differs from its approved base/);
});

test('Feedback managed files support exact install, update and drift detection', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'pf-feedback-package-'));
  try {
    const root = path.join(base, 'package');
    const target = path.join(base, 'consumer');
    const source = path.join(root, 'assets/generated/feedback/adapter.cs');
    fs.mkdirSync(path.dirname(source), { recursive: true });
    fs.mkdirSync(path.join(root, 'assets/feedback'), { recursive: true });
    fs.mkdirSync(target);
    fs.writeFileSync(source, 'v1');
    fs.writeFileSync(path.join(root, 'assets/feedback/distribution.json'), JSON.stringify({
      mappings: [{ source: 'adapter.cs', destination: 'tools/project-forge-feedback-kit/adapter.cs' }]
    }));
    const pkg = {
      root,
      pkg: { name: '@mriekki/project-forge', version: '4.28.0' },
      assets: {
        profiles: { feedback: { components: ['feedback'] } },
        components: { feedback: {
          revision: 'a'.repeat(40), distribution: 'greenfield-project',
          descriptor: 'assets/feedback/distribution.json', sourceRoot: 'assets/generated/feedback'
        } }
      }
    };
    applyProfile(pkg, planProfile(pkg, 'feedback', target), target, 'fixture', 'fixture');
    assert.equal(checkProfile(pkg, 'feedback', target).clean, true);
    const baseline = JSON.parse(fs.readFileSync(path.join(target, 'FEEDBACK_BASELINE.json'), 'utf8'));
    assert.equal(baseline.revision, 'a'.repeat(40));
    fs.writeFileSync(source, 'v2');
    const update = planProfile(pkg, 'feedback', target);
    assert.equal(update.plans[0].rows[0].state, 'KIT_UPDATE');
    applyProfile(pkg, update, target, 'fixture', 'fixture');
    fs.writeFileSync(path.join(target, 'tools/project-forge-feedback-kit/adapter.cs'), 'local drift');
    assert.throws(() => applyProfile(pkg, planProfile(pkg, 'feedback', target), target, 'fixture', 'fixture'), /unsafe drift/);
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});
