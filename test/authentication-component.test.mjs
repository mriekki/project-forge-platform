import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { applyProfile, checkProfile, planProfile } from '../src/engine.mjs';
import { reconcileHouseholdAuthProfile, assertAuthRecoverySourceCoverage } from '../scripts/prepare-package-update.mjs';

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

test('Auth package preparation requires both pinned recovery source distributions', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'pf-recovery-source-gate-'));
  const deployment = path.join(base, 'deployment');
  const authentication = path.join(base, 'authentication');
  const authFiles = [
    ['tools/project_auth_recovery.py', 'tools/project-forge-auth-kit/project_auth_recovery.py'],
    ['docs/AUTH_RECOVERY_RETENTION.md', 'tools/project-forge-auth-kit/docs/AUTH_RECOVERY_RETENTION.md']
  ];
  const deploymentFiles = [
    ['src/project_forge_deployment/auth_recovery_guard.py', 'tools/project-forge-deployment/project_forge_deployment/auth_recovery_guard.py'],
    ['src/project_forge_deployment/auth_recovery_capture.py', 'tools/project-forge-deployment/project_forge_deployment/auth_recovery_capture.py'],
    ['src/project_forge_deployment/auth_recovery_lifecycle.py', 'tools/project-forge-deployment/project_forge_deployment/auth_recovery_lifecycle.py']
  ];
  function seed(root, files, id) {
    for (const [source] of files) {
      const file = path.join(root, source);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, 'synthetic nonsecret fixture');
    }
    const file = path.join(root, 'distributions', 'greenfield-project.json');
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({
      schemaVersion: 1, name: 'greenfield-project',
      ...(id === 'authentication' ? { component: 'authentication' } : {}),
      mappings: files.map(([source, destination]) => ({ source, destination }))
    }));
    return file;
  }
  try {
    const a = seed(authentication, authFiles, 'authentication');
    const d = seed(deployment, deploymentFiles, 'deployment');
    assert.equal(assertAuthRecoverySourceCoverage(deployment, authentication), undefined);
    fs.rmSync(path.join(deployment, deploymentFiles[2][0]));
    assert.throws(() => assertAuthRecoverySourceCoverage(deployment, authentication), /Missing accepted deployment recovery source/);
    fs.writeFileSync(path.join(deployment, deploymentFiles[2][0]), 'synthetic nonsecret fixture');
    const original = fs.readFileSync(a, 'utf8');
    const broken = JSON.parse(original);
    broken.mappings = broken.mappings.slice(0, 1);
    fs.writeFileSync(a, JSON.stringify(broken));
    assert.throws(() => assertAuthRecoverySourceCoverage(deployment, authentication), /Incomplete authentication recovery source/);
    fs.writeFileSync(a, original);
    const origDeploy = JSON.parse(fs.readFileSync(d, 'utf8'));
    origDeploy.mappings.push({ ...origDeploy.mappings[0] });
    fs.writeFileSync(d, JSON.stringify(origDeploy));
    assert.throws(() => assertAuthRecoverySourceCoverage(deployment, authentication), /duplicate deployment/);
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

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
  assert.match(source, /greenfield-household-project/);
  assert.match(source, /standard\.components\.includes\('authentication'\)/);
  assert.doesNotMatch(source, /for \(const profile of Object\.values\(nextComponents\.profiles\)\)/);
  assert.match(assembler, /--authentication-root/);
  assert.doesNotMatch(workflow, /mriekki\/project-forge-auth-kit/);
  assert.doesNotMatch(workflow, /npm publish/);
  assert.doesNotMatch(workflow, /force-push/);
});

test('First and subsequent Auth-enabled package releases preserve the separate household profile', () => {
  const profiles = {
    'greenfield-project': {
      components: ['core', 'deployment'],
      description: 'Regular Project without optional household authentication'
    }
  };
  reconcileHouseholdAuthProfile(profiles);
  assert.deepEqual(profiles['greenfield-project'].components, ['core', 'deployment']);
  const first = structuredClone(profiles['greenfield-household-project']);
  assert.deepEqual(first.components, ['core', 'deployment', 'authentication']);

  // Re-running preparation for the next Kit version is valid, deterministic
  // and does not accidentally enable Auth for existing standard consumers.
  reconcileHouseholdAuthProfile(profiles);
  assert.deepEqual(profiles['greenfield-household-project'], first);
  assert.deepEqual(profiles['greenfield-project'].components, ['core', 'deployment']);

  // A changed standard profile is reconciled only when the old optional
  // profile still represents exactly the prior standard + Auth structure.
  profiles['greenfield-household-project'].components.push('unreviewed');
  assert.throws(() => reconcileHouseholdAuthProfile(profiles), /unexpected components/);
  assert.deepEqual(profiles['greenfield-project'].components, ['core', 'deployment']);
});

test('Auth release preparation rejects unexpected profile settings and standard-profile contamination', () => {
  const base = { 'greenfield-project': { components: ['core', 'deployment'], label: 'approved' } };
  const unsafeStandard = structuredClone(base);
  unsafeStandard['greenfield-project'].components.push('authentication');
  assert.throws(() => reconcileHouseholdAuthProfile(unsafeStandard), /authentication-free/);

  const changedOptional = structuredClone(base);
  changedOptional['greenfield-household-project'] = {
    components: ['core', 'deployment', 'authentication'], label: 'unreviewed'
  };
  assert.throws(() => reconcileHouseholdAuthProfile(changedOptional), /differs from standard/);

  const missingStandard = {};
  assert.throws(() => reconcileHouseholdAuthProfile(missingStandard), /authentication-free/);
  const noRecoveryDeployment = { 'greenfield-project': { components: ['core'] } };
  assert.throws(() => reconcileHouseholdAuthProfile(noRecoveryDeployment), /authentication-free/);
  const duplicateDeployment = { 'greenfield-project': { components: ['core', 'deployment', 'deployment'] } };
  assert.throws(() => reconcileHouseholdAuthProfile(duplicateDeployment), /authentication-free/);
});
