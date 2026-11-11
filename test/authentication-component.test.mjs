import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { applyProfile, checkProfile, planProfile } from '../src/engine.mjs';

function fixture() {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'pf-auth-package-contract-'));
  const source = path.join(base, 'package');
  const target = path.join(base, 'consumer');
  fs.mkdirSync(path.join(source, 'assets', 'authentication'), { recursive: true });
  fs.mkdirSync(path.join(source, 'assets', 'generated', 'authentication', 'src'), { recursive: true });
  fs.mkdirSync(target);
  fs.writeFileSync(path.join(source, 'assets', 'authentication', 'distribution.json'), JSON.stringify({
    schemaVersion: 1,
    name: 'greenfield-project',
    component: 'authentication',
    mappings: [{
      source: 'src/Runtime.cs',
      destination: 'tools/project-forge-auth-kit/src/Runtime.cs'
    }]
  }));
  const file = path.join(source, 'assets', 'generated', 'authentication', 'src', 'Runtime.cs');
  fs.writeFileSync(file, 'approved C# runtime v1\n');
  const pkg = {
    root: source,
    pkg: { name: '@mriekki/project-forge', version: '4.27.0' },
    assets: {
      package: '@mriekki/project-forge', version: '4.27.0',
      profiles: { 'greenfield-project': { components: ['authentication'] } },
      components: {
        authentication: {
          revision: 'a'.repeat(40),
          distribution: 'greenfield-project',
          descriptor: 'assets/authentication/distribution.json',
          sourceRoot: 'assets/generated/authentication'
        }
      }
    }
  };
  return { base, target, file, pkg };
}

test('Authentication Kit is an independent exact-revision managed component, not a private repo pointer', () => {
  const f = fixture();
  try {
    const plan = planProfile(f.pkg, 'greenfield-project', f.target);
    assert.deepEqual(plan.plans.map(x => x.componentId), ['authentication']);
    assert.equal(plan.unsafe.length, 0);
    assert.equal(plan.plans[0].rows[0].state, 'ADD');
    const receipt = applyProfile(f.pkg, plan, f.target, 'test-consumer', 'Bootstrap pinned');
    assert.equal(receipt.components.authentication.revision, 'a'.repeat(40));
    const auth = JSON.parse(fs.readFileSync(path.join(f.target, 'AUTHENTICATION_BASELINE.json')));
    assert.equal(auth.component, 'authentication');
    assert.equal(auth.revision, 'a'.repeat(40));
    assert.equal(Object.hasOwn(auth, 'repository'), false);
    assert.equal(checkProfile(f.pkg, 'greenfield-project', f.target).clean, true);

    fs.writeFileSync(f.file, 'approved C# runtime v2\n');
    const update = planProfile(f.pkg, 'greenfield-project', f.target);
    assert.equal(update.plans[0].rows[0].state, 'KIT_UPDATE');
    assert.equal(update.unsafe.length, 0);
    applyProfile(f.pkg, update, f.target, 'test-consumer', 'Bootstrap pinned');
    assert.equal(checkProfile(f.pkg, 'greenfield-project', f.target).clean, true);

    fs.writeFileSync(path.join(f.target, 'tools/project-forge-auth-kit/src/Runtime.cs'), 'unreviewed local drift\n');
    const drift = planProfile(f.pkg, 'greenfield-project', f.target);
    assert.equal(drift.plans[0].rows[0].state, 'LOCAL_DRIFT');
    assert.equal(drift.unsafe.length, 1);
    assert.throws(() => applyProfile(f.pkg, drift, f.target, 'test-consumer', 'Bootstrap pinned'), /unsafe drift/);
  } finally {
    fs.rmSync(f.base, { recursive: true, force: true });
  }
});

test('Cloud release plumbing is explicitly source-gated and does not publish or embed private source identity', () => {
  const root = new URL('../', import.meta.url);
  const workflow = fs.readFileSync(new URL('.github/workflows/prepare-package-release.yml', root), 'utf8');
  const source = fs.readFileSync(new URL('scripts/prepare-package-update.mjs', root), 'utf8');
  const assembler = fs.readFileSync(new URL('scripts/assemble-assets.mjs', root), 'utf8');
  assert.match(workflow, /authentication_revision:/);
  assert.match(workflow, /AUTHENTICATION_SOURCE_REPOSITORY/);
  assert.match(workflow, /PROJECT_FORGE_SOURCE_TOKEN/);
  assert.match(workflow, /Verify exact component main revisions/);
  assert.match(workflow, /--authentication-root/);
  assert.match(source, /assertExactAcceptedMain\(args\.authenticationRoot/);
  assert.match(source, /assertExpectedOrigin\(authentication.root/);
  assert.match(source, /'authentication'/);
  assert.match(assembler, /--authentication-root/);
  assert.doesNotMatch(workflow, /mriekki\/project-forge-auth-kit/);
  assert.doesNotMatch(workflow, /npm publish/);
  assert.doesNotMatch(workflow, /force-push/);
});
