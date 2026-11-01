import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const schemaPath = 'chatgpt/bootstrap-contracts/project-requirements.schema.json';
const validatorPath = 'chatgpt/bootstrap-contracts/project_requirements.py';

function canonicalGitBlob(relative) {
  return execFileSync('git', ['show', `HEAD:${relative}`], { encoding: null });
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

test('portable requirements public mirrors expose stable digest evidence and an executable canonical validator', () => {
  const schema = canonicalGitBlob(schemaPath);
  const validator = canonicalGitBlob(validatorPath);
  console.log(`PORTABLE_REQUIREMENTS_SCHEMA_SHA256 ${sha256(schema)}`);
  console.log(`PORTABLE_REQUIREMENTS_VALIDATOR_SHA256 ${sha256(validator)}`);

  const root = mkdtempSync(join(tmpdir(), 'project-forge-portable-requirements-'));
  try {
    const validatorFile = join(root, 'project_requirements.py');
    const sampleFile = join(root, 'PROJECT_REQUIREMENTS.json');
    writeFileSync(validatorFile, validator);
    writeFileSync(sampleFile, JSON.stringify({
      schemaVersion: 1,
      state: 'review',
      source: {
        repository: 'mriekki/example-project',
        commit: '0000000000000000000000000000000000000000',
      },
      project: {
        name: 'Example Project',
        description: 'Portable requirements validator smoke fixture',
      },
      product: {
        sourcePath: 'docs/product/PRODUCT_BRIEF.md',
        goal: 'Validate the canonical portable requirements contract',
        users: ['Builder'],
        nonGoals: [],
        successCriteria: ['Canonical validation passes'],
      },
      features: [],
      roadmap: { milestones: [] },
      sourceArtifacts: [],
    }, null, 2));

    const result = spawnSync('python', [validatorFile, sampleFile], {
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stdout, /^VALID PROJECT_REQUIREMENTS\.json state=review /m);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
