import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

test('release preparation runs canonical and package-owned Auth recovery safety on exact pinned Deployment source', () => {
  const workflow = read('.github/workflows/prepare-package-release.yml');
  const sourceCheck = workflow.indexOf('- name: Verify exact component main revisions');
  const canonical = workflow.indexOf('- name: Verify exact Deployment recovery safety before package preparation');
  const assembly = workflow.indexOf('- name: Assemble and verify exact package assets');
  const packageSource = workflow.indexOf('node scripts/verify-assets.mjs', assembly);
  const packagedTest = workflow.indexOf('test_packaged_deployment_recovery_safety.py', assembly);
  const otherTests = workflow.indexOf('npm test', assembly);
  const branchPush = workflow.indexOf('- name: Commit and push prepared release branch');

  assert.ok(sourceCheck >= 0 && sourceCheck < canonical,
    'exact Deployment main SHA and clean tree must be checked first');
  assert.ok(canonical < assembly && canonical >= 0,
    'canonical recovery tests must pass before assembly');
  assert.ok(assembly < packageSource && packageSource < packagedTest,
    'verify exact assembled asset hashes before package-owned behavior tests');
  assert.ok(packagedTest < otherTests && otherTests < branchPush,
    'run both package behavior and npm tests before pushing prepared branch');
  assert.match(workflow, /test_auth_recovery_lifecycle\.py/);
  assert.match(workflow, /test_auth_recovery_retention\.py/);
  assert.match(workflow, /PYTHONPATH: \.release-sources\/deployment\/src/);
  assert.match(workflow, /PROJECT_FORGE_PACKAGED_DEPLOYMENT_ROOT=assets\/generated\/deployment\/src/);
  assert.match(workflow, /PYTHONPATH=assets\/generated\/deployment\/src/);
  assert.match(workflow, /python -m unittest discover -s test\/fixtures/);
  assert.match(workflow, /python-version: '3\.11'/);
  assert.match(workflow, /node scripts\/verify-assets\.mjs/);
  // This is the unpublished preparation workflow: never insert npm publish
  // or mutate the consuming Project merely to qualify tests.
  assert.doesNotMatch(workflow, /\bnpm publish\b/);
});

test('npm publish reruns exact canonical and assembled recovery safety before publication', () => {
  const workflow = read('.github/workflows/npm-publish.yml');
  const checkouts = workflow.indexOf('- name: Verify exact private source checkouts');
  const assemble = workflow.indexOf('- name: Prepare reproducible release candidate');
  const preflight = workflow.indexOf('- name: Reverify canonical and packaged Auth recovery before any npm publish');
  const manifest = workflow.indexOf('- name: Verify release manifest matches authorization');
  const publish = workflow.indexOf('- name: Publish exact package with npm Trusted Publishing');
  assert.ok(checkouts >= 0 && checkouts < assemble);
  assert.ok(assemble < preflight && preflight < manifest && manifest < publish,
    'the recovery gate must run after exact release assembly and before the npm publish step');
  assert.match(workflow, /test_auth_recovery_lifecycle\.py/);
  assert.match(workflow, /test_auth_recovery_retention\.py/);
  assert.match(workflow, /node scripts\/verify-assets\.mjs/);
  assert.match(workflow, /PROJECT_FORGE_PACKAGED_DEPLOYMENT_ROOT=assets\/generated\/deployment\/src/);
  assert.match(workflow, /test_packaged_deployment_recovery_safety\.py/);
  assert.match(workflow, /python-version: '3\.11'/);
});

test('package-owned safety tests target packaged code and all four handoff risk areas', () => {
  const fixture = read('test/fixtures/test_packaged_deployment_recovery_safety.py');
  const components = JSON.parse(read('assets/components.json'));
  const distribution = JSON.parse(read('assets/deployment/distribution.json'));
  assert.equal(components.components.deployment.sourceRoot,
    'assets/generated/deployment');
  const mappings = new Map(distribution.mappings.map(x => [x.source, x.destination]));
  for (const module of ['auth_recovery_lifecycle', 'auth_recovery_retention']) {
    assert.equal(mappings.get(`src/project_forge_deployment/${module}.py`),
      `tools/project-forge-deployment/project_forge_deployment/${module}.py`);
  }
  for (const testName of [
    'test_interrupted_exact_container_already_running_is_not_started_again',
    'test_replacement_container_identity_is_refused_and_journal_survives',
    'test_retention_inventory_drift_refuses_deletion_and_started_receipt',
    'test_partial_deletion_has_private_failure_not_completion_receipt',
    'test_interrupted_deletion_leaves_start_only_and_never_claims_success'
  ]) {
    assert.match(fixture, new RegExp(`def ${testName}\\(`));
  }
  assert.match(fixture, /PROJECT_FORGE_PACKAGED_DEPLOYMENT_ROOT/);
  assert.match(fixture, /module\.__file__/);
  assert.match(fixture, /\.is_relative_to\(root\)/);
  assert.match(fixture, /KeyboardInterrupt/);
  assert.match(fixture, /failed-or-unverified/);
  assert.doesNotMatch(fixture, /subprocess\.run\(|docker\s+start|docker\s+stop/);
});
