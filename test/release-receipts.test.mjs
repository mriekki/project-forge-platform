import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { evaluateAlignment } from '../scripts/check-chatgpt-contract-alignment.mjs';
import {
  loadReleaseReceipt,
  parseArgs,
  validateReleaseReceipt,
} from '../scripts/release-receipt.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const RECEIPTS = path.join(ROOT, 'release', 'receipts');

test('checked-in release receipts are valid privacy-safe durable evidence', async () => {
  const files = fs.readdirSync(RECEIPTS)
    .filter((name) => /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\.json$/.test(name))
    .sort();

  assert.ok(files.length > 0, 'at least one durable release receipt must exist');

  for (const filename of files) {
    const version = filename.slice(0, -'.json'.length);
    const receipt = await loadReleaseReceipt(version, ROOT);
    assert.equal(receipt.package.version, version);

    const serialized = JSON.stringify(receipt);
    assert.doesNotMatch(serialized, /mriekki\/project-forge-core/);
    assert.doesNotMatch(serialized, /mriekki\/project-forge-deployment-kit/);
    assert.doesNotMatch(serialized, /sourceRepository/);
  }
});

test('stable contract alignment verifies the durable receipt for the selected package', async () => {
  const descriptor = JSON.parse(fs.readFileSync(path.join(ROOT, 'chatgpt', 'current.json'), 'utf8'));
  const selectedVersion = descriptor.generation.packageVersion;
  const result = evaluateAlignment(selectedVersion, descriptor);
  assert.equal(result.aligned, true);

  const receipt = await loadReleaseReceipt(selectedVersion, ROOT);
  assert.equal(receipt.package.version, selectedVersion);
});

test('release receipt validation rejects incomplete publication evidence', () => {
  const valid = JSON.parse(fs.readFileSync(path.join(RECEIPTS, '4.11.0.json'), 'utf8'));
  const invalid = structuredClone(valid);
  invalid.publication.neutralNpxSmoke = 'unknown';
  assert.throws(
    () => validateReleaseReceipt(invalid, '4.11.0'),
    /publication\.neutralNpxSmoke must equal verified/,
  );
});

test('release receipt CLI requires one exact semantic version', () => {
  assert.deepEqual(parseArgs(['--version', '4.11.0', '--json']), { version: '4.11.0', json: true });
  assert.throws(() => parseArgs(['--version', 'latest']), /version is invalid/);
  assert.throws(() => parseArgs([]), /version is invalid/);
});

test('Auth release receipts require accepted exact component revision and Auth CI', () => {
  const base = JSON.parse(fs.readFileSync(path.join(RECEIPTS, '4.26.1.json'), 'utf8'));
  const auth = structuredClone(base);
  auth.components.authentication = { revision: 'a'.repeat(40) };
  auth.ci.authenticationMain = { result: 'success', workflowRunId: 123456 };
  assert.equal(validateReleaseReceipt(auth).components.authentication.revision, 'a'.repeat(40));

  const noAuthCI = structuredClone(auth);
  delete noAuthCI.ci.authenticationMain;
  assert.throws(() => validateReleaseReceipt(noAuthCI), /ci.authenticationMain/);

  const badRevision = structuredClone(auth);
  badRevision.components.authentication.revision = 'main';
  assert.throws(() => validateReleaseReceipt(badRevision), /components.authentication.revision/);

  const exposedRepo = structuredClone(auth);
  exposedRepo.components.authentication.sourceRepository = 'private/repository';
  assert.throws(() => validateReleaseReceipt(exposedRepo), /forbidden component source field/);

  const extraneous = structuredClone(auth);
  extraneous.components.unknown = { revision: 'b'.repeat(40) };
  assert.throws(() => validateReleaseReceipt(extraneous), /exactly Core, Deployment and optional Authentication/);

  const legacyMislabel = structuredClone(base);
  legacyMislabel.ci.authenticationMain = { result: 'success', workflowRunId: 123456 };
  assert.throws(() => validateReleaseReceipt(legacyMislabel), /Non-Auth release receipt/);
});
