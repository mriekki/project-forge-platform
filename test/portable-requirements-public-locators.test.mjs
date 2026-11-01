import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const schemaMirrorPath = 'chatgpt/bootstrap-contracts/project-requirements.schema.json';
const validatorMirrorPath = 'chatgpt/bootstrap-contracts/project_requirements.py';
const platformSource = 'e76b6bd488448a76ae5f4cd5195d11e75fdb45b8';
const bootstrapRevision = '8754b1a06f23c61f3fa437fd32690f5d3322325a';

function canonicalGitBlob(relative) {
  return execFileSync('git', ['show', `HEAD:${relative}`], { encoding: null });
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

test('stable descriptor exposes digest-verified immutable portable requirements locators', () => {
  const descriptor = JSON.parse(readFileSync('chatgpt/current.json', 'utf8'));
  const bootstrap = descriptor.generation.bootstrap;
  const portable = bootstrap.portableRequirements;

  assert.equal(bootstrap.revision, bootstrapRevision);
  assert.equal(portable.bootstrapRevision, bootstrap.revision);
  assert.equal(portable.schema.path, 'schemas/project-requirements.schema.json');
  assert.equal(portable.validator.path, 'tools/project_requirements.py');

  assert.equal(
    portable.schema.url,
    `https://raw.githubusercontent.com/mriekki/project-forge-platform/${platformSource}/${schemaMirrorPath}`,
  );
  assert.equal(
    portable.validator.url,
    `https://raw.githubusercontent.com/mriekki/project-forge-platform/${platformSource}/${validatorMirrorPath}`,
  );
  assert.doesNotMatch(portable.schema.url, /\/main\//);
  assert.doesNotMatch(portable.validator.url, /\/main\//);
  assert.doesNotMatch(portable.schema.url, /project-forge-bootstrap/);
  assert.doesNotMatch(portable.validator.url, /project-forge-bootstrap/);

  assert.equal(sha256(canonicalGitBlob(schemaMirrorPath)), portable.schema.sha256);
  assert.equal(sha256(canonicalGitBlob(validatorMirrorPath)), portable.validator.sha256);
});

test('advertised canonical portable requirements validator accepts a review-state canonical fixture', () => {
  const descriptor = JSON.parse(readFileSync('chatgpt/current.json', 'utf8'));
  const portable = descriptor.generation.bootstrap.portableRequirements;
  const validator = canonicalGitBlob(validatorMirrorPath);
  assert.equal(sha256(validator), portable.validator.sha256);

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

    const result = spawnSync('python', [validatorFile, sampleFile], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stdout, /^VALID PROJECT_REQUIREMENTS\.json state=review /m);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
