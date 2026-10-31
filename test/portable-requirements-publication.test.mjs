import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaPath = 'chatgpt/bootstrap-contracts/project-requirements.schema.json';
const validatorPath = 'chatgpt/bootstrap-contracts/project_requirements.py';

async function text(relative) {
  return readFile(path.join(root, relative), 'utf8');
}

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
