import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaPath = 'chatgpt/bootstrap-contracts/project-requirements.schema.json';
const validatorPath = 'chatgpt/bootstrap-contracts/project_requirements.py';
const bootstrapSchemaBlobSha = 'cfcde2662742e51dc0f4addb5f2c048a18b32b39';
const bootstrapValidatorBlobSha = '0e045087f4e123ba6f8fde3875d38ba46a193593';

async function text(relative) {
  return readFile(path.join(root, relative), 'utf8');
}

function canonicalGitBlobSha(relative) {
  const result = spawnSync('git', ['rev-parse', `HEAD:${relative}`], {
    cwd: root,
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, `Unable to resolve canonical Git blob ${relative}: ${result.stderr ?? ''}`);
  return result.stdout.trim();
}

test('portable requirements mirrors preserve exact Bootstrap source bytes', () => {
  assert.equal(canonicalGitBlobSha(schemaPath), bootstrapSchemaBlobSha);
  assert.equal(canonicalGitBlobSha(validatorPath), bootstrapValidatorBlobSha);
});

test('portable requirements mirrors are public-distribution safe', async () => {
  const schemaText = await text(schemaPath);
  const validator = await text(validatorPath);
  const schema = JSON.parse(schemaText);

  assert.equal(
    schema.$id,
    'https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/bootstrap-contracts/project-requirements.schema.json',
  );
  assert.deepEqual(
    schema.required,
    ['schemaVersion', 'state', 'source', 'project', 'product', 'features', 'roadmap', 'sourceArtifacts'],
  );
  assert.doesNotMatch(schemaText, /project-forge-bootstrap/);
  assert.doesNotMatch(validator, /project-forge-bootstrap/);
  assert.match(validator, /def validate_project_requirements/);
  assert.match(validator, /--require-approved/);
});
