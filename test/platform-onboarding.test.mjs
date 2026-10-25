import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import { evaluateAlignment } from '../scripts/check-chatgpt-contract-alignment.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function text(relative) {
  return readFile(path.join(root, relative), 'utf8');
}

function descriptor(packageVersion = '4.4.2') {
  return {
    schemaVersion: 1,
    channel: 'stable',
    contractVersion: 13,
    snapshotPath: 'chatgpt/contracts/v13',
    generation: {
      manifestFilename: 'PROJECT_BOOTSTRAP.json',
      bootstrap: {
        revision: 'a'.repeat(40),
        protocolVersion: 12,
        catalogVersion: 12,
      },
      package: '@mriekki/project-forge',
      packageVersion,
      profile: 'greenfield-project',
      bootstrapProtocolVersion: 12,
    },
  };
}

test('public contract alignment guard reports aligned and stale states explicitly', () => {
  const aligned = evaluateAlignment('4.4.2', descriptor());
  assert.equal(aligned.aligned, true);
  assert.match(aligned.message, /Public ChatGPT contract: ALIGNED/);
  assert.match(aligned.message, /Bootstrap a{40}/);

  const stale = evaluateAlignment('4.4.3', descriptor());
  assert.equal(stale.aligned, false);
  assert.match(stale.message, /PUBLIC CHATGPT CONTRACT ADVANCEMENT REQUIRED/);
  assert.match(stale.message, /Package version: 4\.4\.3/);
  assert.match(stale.message, /Public contract package version: 4\.4\.2/);
});

test('public contract alignment guard validates the complete privacy-safe generation tuple', () => {
  const malformedRevision = descriptor();
  malformedRevision.generation.bootstrap.revision = 'main';
  const revisionResult = evaluateAlignment('4.4.2', malformedRevision);
  assert.equal(revisionResult.aligned, false);
  assert.match(revisionResult.message, /exact lowercase 40-character revision/);

  const leakedTopology = descriptor();
  leakedTopology.generation.bootstrap.repository = 'private/bootstrap';
  const topologyResult = evaluateAlignment('4.4.2', leakedTopology);
  assert.equal(topologyResult.aligned, false);
  assert.match(topologyResult.message, /private source topology/);

  const protocolMismatch = descriptor();
  protocolMismatch.generation.bootstrapProtocolVersion = 11;
  const protocolResult = evaluateAlignment('4.4.2', protocolMismatch);
  assert.equal(protocolResult.aligned, false);
  assert.match(protocolResult.message, /does not match/);

  const floatingPackage = descriptor('^4.4.2');
  const floatingResult = evaluateAlignment('4.4.2', floatingPackage);
  assert.equal(floatingResult.aligned, false);
  assert.match(floatingResult.message, /exact semantic version/);
});

test('ChatGPT setup resolves the canonical immutable Project instruction instead of duplicating it', async () => {
  const setup = await text('chatgpt/SETUP.md');
  assert.match(setup, /PROJECT_INSTRUCTIONS\.md/);
  assert.match(setup, /snapshotPath/);
  assert.match(setup, /copy the fenced instruction text \*\*verbatim\*\*/);
  assert.doesNotMatch(setup, /At the beginning of a Project Forge coding workflow, load:/);
});

test('handoff migration guidance is generic and repository-authoritative', async () => {
  const migration = await text('chatgpt/HANDOFF_MIGRATION.md');
  assert.match(migration, /generated Project repositories as durable Project state/);
  assert.match(migration, /New Builders should use invitation \+ current public-contract onboarding directly/);
  assert.doesNotMatch(migration, /For Mark and Kyle/);
  assert.doesNotMatch(migration, /such as Daniel/);
  assert.doesNotMatch(migration, /Lean operating-model/);
});

test('alignment workflow runs after successful npm publication and after descriptor changes', async () => {
  const workflow = await text('.github/workflows/chatgpt-contract-alignment.yml');
  assert.match(workflow, /workflows: \["Publish npm Package"\]/);
  assert.match(workflow, /github\.event\.workflow_run\.conclusion == 'success'/);
  assert.match(workflow, /chatgpt\/current\.json/);
  assert.match(workflow, /check-chatgpt-contract-alignment\.mjs/);
});
