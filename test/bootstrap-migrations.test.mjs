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

function generatedConsumer() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-bootstrap-migration-'));
  fs.writeFileSync(path.join(root, 'PROJECT_BOOTSTRAP.json'), '{}\n');
  const destination = path.join(root, DESTINATION);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(OLD_FIXTURE, destination);
  return { root, destination };
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

test('bundled migration asset records exact Bootstrap provenance and identity', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/bootstrap-migrations/managed-baseline-verifier/manifest.json'), 'utf8'));
  const asset = fs.readFileSync(path.join(ROOT, manifest.asset));
  assert.equal(manifest.owner, 'bootstrap');
  assert.equal(manifest.source.repository, 'mriekki/project-forge-bootstrap');
  assert.equal(manifest.source.revision, 'b5a83729d211e0492be5368ff7f1e59b63986419');
  assert.equal(manifest.source.path, 'migration-assets/package-workspace/check-managed-baselines.py');
  assert.equal(manifest.targetGitBlob, TARGET_BLOB);
  assert(manifest.supportedPredecessorGitBlobs.includes(OLD_BLOB));
  assert.equal(gitBlobSha(asset), TARGET_BLOB);
});
