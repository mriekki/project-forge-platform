import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function readJson(relative) {
  return JSON.parse(await readFile(path.join(root, relative), 'utf8'));
}

function canonicalGitBlob(relative) {
  return execFileSync('git', ['show', `HEAD:${relative}`], { cwd: root, encoding: null });
}

function sha256(relative) {
  return createHash('sha256').update(canonicalGitBlob(relative)).digest('hex');
}

test('public adoption projection matches the advertised protocol shape', async () => {
  const descriptor = await readJson('chatgpt/current.json');
  const adoption = await readJson('chatgpt/adoption-contracts/project-adoption.schema.json');
  const operations = await readJson('chatgpt/adoption-contracts/project-forge-operations.schema.json');

  assert.equal(adoption.properties.adoptionKit.properties.protocolVersion.const, descriptor.adoption.kit.protocolVersion);
  assert.equal(adoption.properties.state.const, 'approved');
  assert.equal(adoption.properties.repositoryRelationship.properties.upstreamWrites.const, false);
  assert.equal(adoption.properties.operationsProfile.oneOf[1].$ref, 'project-forge-operations.schema.json');
  assert.deepEqual(
    adoption.properties.engineeringContext.properties.repositoryWorkflow.required,
    ['commitMessage', 'pullRequest'],
  );
  assert.deepEqual(
    adoption.properties.engineeringContext.properties.repositoryWorkflow.properties.pullRequest.properties.body.oneOf.map(
      (shape) => shape.properties.mode.const,
    ),
    ['project-forge-summary', 'repository-template'],
  );
  assert.deepEqual(
    operations.properties.status.enum,
    ['human-confirmed', 'user-corrected'],
  );
  assert.equal(
    sha256('chatgpt/adoption-contracts/project-adoption.schema.json'),
    descriptor.adoption.contract.schema.sha256,
  );
  assert.equal(
    sha256('chatgpt/adoption-contracts/project-forge-operations.schema.json'),
    descriptor.adoption.contract.operationsSchema.sha256,
  );
});
