import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workflow = fs.readFileSync(path.join(ROOT, '.github/workflows/prepare-package-release.yml'), 'utf8');
const candidate = fs.readFileSync(path.join(ROOT, 'scripts/qualify-auth-candidate.py'), 'utf8');

test('Auth candidate qualification is opt-in and occurs before release branch commit', () => {
  const qualification = workflow.indexOf('Qualify real unpublished Auth candidate');
  const commit = workflow.indexOf('Commit and push prepared release branch');
  assert.ok(qualification > 0 && qualification < commit);
  assert.match(workflow.slice(qualification, commit), /if: \$\{\{ steps\.request\.outputs\.authentication_revision != '' \}\}/);
  assert.match(workflow.slice(qualification, commit), /python3 scripts\/qualify-auth-candidate\.py/);
  assert.match(workflow, /dotnet-version: '10\.0\.x'/);
  assert.doesNotMatch(workflow.slice(qualification, commit), /npm publish/);
  assert.match(workflow, /Record owner-initiated unpublished preparation run/);
  assert.match(workflow, /Report failed preparation with a durable run link/);
  assert.match(workflow, /BLOCKED: unpublished Project Forge preparation failed/);
});

test('Actual-package qualification requires generation, repair and build without readiness overclaim', () => {
  assert.match(candidate, /npm", "pack"/);
  assert.match(candidate, /"npm", "install"/);
  assert.match(candidate, /bootstrap\.require_packaged_auth\(/);
  assert.match(candidate, /bootstrap\.materialize_reference_project\(/);
  assert.match(candidate, /"dotnet", "build"/);
  assert.match(candidate, /"repair"/);
  assert.match(candidate, /_prove_package_runtime_recovery\(/);
  assert.match(candidate, /tests\/generated_project_recovery_proof\.py/);
  assert.match(candidate, /harness\.prove_generated_project_auth_recovery\(/);
  assert.match(candidate, /"generatedRuntimeRecoveryProven": recovery\["isolatedRestoreVerified"\]/);
  assert.match(candidate, /"dockerQuiescenceVerified"/);
  assert.match(candidate, /"scheduledBackupVerified"/);
  assert.match(candidate, /"alertInboxReceiptVerified"/);
  assert.match(candidate, /"applicationRecoveryReady": False/);
  assert.match(candidate, /"npmPublished": False/);
  assert.match(candidate, /"productionModified": False/);
});
