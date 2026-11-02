import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { applyBootstrapMigrations, gitBlobSha, planBootstrapMigrations } from '../src/bootstrap-migrations.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OLD_FIXTURE = path.join(ROOT, 'test/fixtures/bootstrap-verifiers/schema1-check-managed-baselines.py');
const DESTINATION = 'tools/project-forge-package/check-managed-baselines.py';
const OLD_BLOB = 'f7ccfc0e8efaac4d6aed6ed5d8e2130d4fb3dc9d';
const TARGET_BLOB = '26496854ed5d6ad47c7b6136078b2114473ac773';
const WSL_PREDECESSOR_BOOTSTRAP = '0c45eb332a815ad79ea061443f337500b9dc5712';
const WSL_LAUNCHER_BOOTSTRAP = '173203baaf36935d04eb81c89f1d016131a40442';
const WSL_PREVIOUS_RUNTIME_BOOTSTRAP = '9f0f7fd4e0e2220250f6fd5b035706a7d15834af';
const WSL_RUNTIME_BOOTSTRAP = '043b3b2a0e3ba03b8d18666bb3fef59c588bfa16';
const WSL_LAUNCHER = 'scripts/setup.sh';
const WSL_RUNTIME = 'tools/dev-environment/setup-wsl.py';
const WSL_LAUNCHER_BLOB = '4e8c48a3d33c6a8ae4534ec860c2ee0205e417aa';
const WSL_OLDER_RUNTIME_BLOB = '6731910246fb99887c58b9f3a8a14fec1bf02c01';
const WSL_PREVIOUS_RUNTIME_BLOB = '883f7bbadd2de4bc0dcb601ee2285f88a0085b52';
const WSL_RUNTIME_BLOB = '0b959b4e85508016f6e8c12d403a94b2eed46c1f';

function generatedConsumer() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-bootstrap-migration-'));
  fs.writeFileSync(path.join(root, 'PROJECT_BOOTSTRAP.json'), '{}\n');
  const destination = path.join(root, DESTINATION);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(OLD_FIXTURE, destination);
  return { root, destination };
}

function wslGeneratedConsumer() {
  const { root, destination } = generatedConsumer();
  fs.writeFileSync(path.join(root, 'PROJECT_BOOTSTRAP.json'), JSON.stringify({
    bootstrap: { commit: WSL_PREDECESSOR_BOOTSTRAP }
  }, null, 2) + '\n');
  const launcher = path.join(root, WSL_LAUNCHER);
  fs.mkdirSync(path.dirname(launcher), { recursive: true });
  fs.copyFileSync(path.join(ROOT, 'assets/bootstrap-migrations/wsl-setup/setup.sh'), launcher);
  fs.mkdirSync(path.join(root, 'tools/dev-environment'), { recursive: true });
  return { root, destination, launcher, runtime: path.join(root, WSL_RUNTIME) };
}

const packageData = { root: ROOT };

test('known schema-1 Bootstrap verifier is planned and migrated exactly', () => {
  assert.equal(gitBlobSha(fs.readFileSync(OLD_FIXTURE)), OLD_BLOB);
  const { root, destination } = generatedConsumer();
  const plan = planBootstrapMigrations(packageData, root);
  assert.equal(plan.unsafe.length, 0);
  assert.deepEqual(plan.rows.map((row) => [row.state, row.path, row.fromGitBlob, row.toGitBlob]), [[
    'MIGRATE_BOOTSTRAP_VERIFIER', DESTINATION, OLD_BLOB, TARGET_BLOB
  ]]);
  applyBootstrapMigrations(packageData, plan, root);
  assert.equal(gitBlobSha(fs.readFileSync(destination)), TARGET_BLOB);
  const after = planBootstrapMigrations(packageData, root);
  assert.deepEqual(after, { rows: [], unsafe: [] });
});

test('unknown generated verifier fails preflight without overwrite', () => {
  const { root, destination } = generatedConsumer();
  fs.writeFileSync(destination, '# consumer customization\n');
  const before = fs.readFileSync(destination);
  const plan = planBootstrapMigrations(packageData, root);
  assert.equal(plan.rows.length, 0);
  assert.equal(plan.unsafe.length, 1);
  assert.equal(plan.unsafe[0].state, 'BOOTSTRAP_MIGRATION_UNSUPPORTED');
  assert.deepEqual(fs.readFileSync(destination), before);
});

test('missing generated verifier fails preflight', () => {
  const { root, destination } = generatedConsumer();
  fs.unlinkSync(destination);
  const plan = planBootstrapMigrations(packageData, root);
  assert.equal(plan.rows.length, 0);
  assert.equal(plan.unsafe[0].state, 'BOOTSTRAP_MIGRATION_UNSUPPORTED');
});

test('package-only consumer without PROJECT_BOOTSTRAP is outside Bootstrap migration ownership', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-package-only-'));
  assert.deepEqual(planBootstrapMigrations(packageData, root), { rows: [], unsafe: [] });
});

test('bundled verifier migration asset records exact privacy-safe Bootstrap provenance and identity', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/bootstrap-migrations/managed-baseline-verifier/manifest.json'), 'utf8'));
  const asset = fs.readFileSync(path.join(ROOT, manifest.asset));
  assert.equal(manifest.owner, 'bootstrap');
  assert.equal(manifest.source.component, 'bootstrap');
  assert.equal(manifest.source.revision, 'b5a83729d211e0492be5368ff7f1e59b63986419');
  assert.equal(manifest.source.artifact, 'migration-assets/package-workspace/check-managed-baselines.py');
  assert.equal(Object.hasOwn(manifest.source, 'repository'), false);
  assert.equal(manifest.targetGitBlob, TARGET_BLOB);
  assert(manifest.supportedPredecessorGitBlobs.includes(OLD_BLOB));
  assert.equal(gitBlobSha(asset), TARGET_BLOB);
});

test('recognized generated Project can add the WSL setup runtime without changing Bootstrap provenance', () => {
  const { root, destination, runtime } = wslGeneratedConsumer();
  // Keep the legacy verifier out of the migration plan for this focused test.
  fs.copyFileSync(path.join(ROOT, 'assets/bootstrap-migrations/managed-baseline-verifier/check-managed-baselines.py'), destination);

  const plan = planBootstrapMigrations(packageData, root);
  assert.equal(plan.unsafe.length, 0);
  assert.deepEqual(plan.rows.map((row) => [row.state, row.path, row.toGitBlob]), [[
    'ADD_BOOTSTRAP_FILE', WSL_RUNTIME, WSL_RUNTIME_BLOB
  ]]);

  applyBootstrapMigrations(packageData, plan, root);
  assert.equal(gitBlobSha(fs.readFileSync(runtime)), WSL_RUNTIME_BLOB);
  assert.equal(JSON.parse(fs.readFileSync(path.join(root, 'PROJECT_BOOTSTRAP.json'), 'utf8')).bootstrap.commit, WSL_PREDECESSOR_BOOTSTRAP);
  assert.deepEqual(planBootstrapMigrations(packageData, root), { rows: [], unsafe: [] });
});

test('WSL Bootstrap migration assets are exact and recognize supported prior setup runtimes', () => {
  const launcherManifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/bootstrap-migrations/wsl-setup/setup-launcher.manifest.json'), 'utf8'));
  const runtimeManifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/bootstrap-migrations/wsl-setup/setup-wsl.manifest.json'), 'utf8'));
  const launcher = fs.readFileSync(path.join(ROOT, launcherManifest.asset));
  const runtime = fs.readFileSync(path.join(ROOT, runtimeManifest.asset));

  assert.equal(launcherManifest.source.revision, WSL_LAUNCHER_BOOTSTRAP);
  assert.equal(runtimeManifest.source.revision, WSL_RUNTIME_BOOTSTRAP);
  assert.deepEqual(launcherManifest.supportedBootstrapRevisions, [WSL_PREDECESSOR_BOOTSTRAP]);
  assert.deepEqual(runtimeManifest.supportedBootstrapRevisions, [
    WSL_PREDECESSOR_BOOTSTRAP,
    WSL_LAUNCHER_BOOTSTRAP,
    WSL_PREVIOUS_RUNTIME_BOOTSTRAP
  ]);
  assert(launcherManifest.supportedPredecessorGitBlobs.includes('ec941c079da066785ac628d6bbb7dd6b668494f2'));
  assert(runtimeManifest.supportedPredecessorGitBlobs.includes(WSL_OLDER_RUNTIME_BLOB));
  assert(runtimeManifest.supportedPredecessorGitBlobs.includes(WSL_PREVIOUS_RUNTIME_BLOB));
  assert.equal(runtimeManifest.allowMissing, true);
  assert.equal(gitBlobSha(launcher), WSL_LAUNCHER_BLOB);
  assert.equal(gitBlobSha(runtime), WSL_RUNTIME_BLOB);
});
