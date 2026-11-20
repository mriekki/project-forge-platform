import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';
import { loadReleaseReceipt } from '../scripts/release-receipt.mjs';
import { parseArgs, verifyCandidateHandoff } from '../scripts/verify-candidate-handoff.mjs';

const COMPONENTS = ['core', 'deployment', 'authentication', 'feedback', 'release-notes'];
const PUBLIC_REFERENCE_COMMIT = '74b9462df28faab16bcde7599373f632e2b29626';

async function fixture() {
  const bytes = Buffer.from('disposable unit-test npm archive fixture');
  const hash = crypto.createHash('sha256').update(bytes).digest('hex');
  const receipt = structuredClone(await loadReleaseReceipt('4.35.0'));
  // A unit-test fixture only; NOT a replacement for the real signed public
  // publication receipt or registry integrity verification.
  receipt.artifact.releaseCandidateSha256 = hash;
  const claim = {
    schemaVersion: 1,
    kind: 'project-forge-npm-candidate-handoff',
    status: 'verification-only',
    package: { name: '@mriekki/project-forge', version: '4.35.0' },
    artifact: { filename: 'mriekki-project-forge-4.35.0.tgz', sha256: hash, sizeBytes: bytes.length },
    components: Object.fromEntries(COMPONENTS.map(id => [id, structuredClone(receipt.components[id])])),
    reference: { platformCommit: PUBLIC_REFERENCE_COMMIT, tarballSha256: hash },
    releaseAuthorized: false,
    productionAuthorized: false,
    identityTrust: 'not-established'
  };
  return { bytes, receipt, claim };
}

test('candidate matches an independently selected previously published receipt without granting trust', async () => {
  const { bytes, claim, receipt } = await fixture();
  const result = verifyCandidateHandoff(claim, bytes, receipt, PUBLIC_REFERENCE_COMMIT);
  assert.equal(result.result, 'MATCHES_EXISTING_PUBLIC_RELEASE');
  assert.equal(result.identityVerified, false);
  assert.equal(result.publicationAuthorized, false);
  assert.equal(result.productionAuthorized, false);
});

test('candidate cannot assert permission to publish or deploy', async () => {
  const { bytes, claim, receipt } = await fixture();
  assert.throws(() => verifyCandidateHandoff({
    ...claim, releaseAuthorized: true
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /Untrusted candidate/);
  assert.throws(() => verifyCandidateHandoff({
    ...claim, productionAuthorized: true
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /Untrusted candidate/);
  assert.throws(() => verifyCandidateHandoff({
    ...claim, identityTrust: 'verified'
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /Untrusted candidate/);
});

test('candidate cannot inject private repository identifiers or unexpected fields', async () => {
  const { bytes, claim, receipt } = await fixture();
  assert.throws(() => verifyCandidateHandoff({
    ...claim, sourceRepository: 'sensitive/private-source'
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /exactly its approved fields/);
  assert.throws(() => verifyCandidateHandoff({
    ...claim, components: {
      ...claim.components,
      core: { ...claim.components.core, repository: 'sensitive/private-source' }
    }
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /exactly its approved fields/);
});

test('tampered archive, incorrect size and changed public receipt fail closed', async () => {
  const { bytes, claim, receipt } = await fixture();
  assert.throws(() => verifyCandidateHandoff(claim, Buffer.concat([bytes, Buffer.from('tampered')]), receipt, PUBLIC_REFERENCE_COMMIT), /archive SHA-256\/size/);
  assert.throws(() => verifyCandidateHandoff({
    ...claim, artifact: { ...claim.artifact, sizeBytes: 1 }
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /archive SHA-256\/size/);
  const untrustedReceipt = structuredClone(receipt);
  untrustedReceipt.artifact.releaseCandidateSha256 = 'a'.repeat(64);
  assert.throws(() => verifyCandidateHandoff(claim, bytes, untrustedReceipt, PUBLIC_REFERENCE_COMMIT), /archive SHA-256\/size/);
});

test('changed revisions, version, or reference commit are rejected', async () => {
  const { bytes, claim, receipt } = await fixture();
  assert.throws(() => verifyCandidateHandoff({
    ...claim, components: {
      ...claim.components, deployment: { revision: 'a'.repeat(40) }
    }
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /deployment revision/);
  assert.throws(() => verifyCandidateHandoff({
    ...claim, package: { ...claim.package, version: '4.36.0' }
  }, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /package differs/);
  assert.throws(() => verifyCandidateHandoff(claim, bytes, receipt, 'f'.repeat(40)), /reference does not match/);
});

test('incomplete candidate or invalid command-line inputs are rejected', async () => {
  const { bytes, claim, receipt } = await fixture();
  const missing = structuredClone(claim);
  delete missing.components['release-notes'];
  assert.throws(() => verifyCandidateHandoff(missing, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /exactly its approved fields/);
  assert.throws(() => verifyCandidateHandoff({...claim, schemaVersion: 2}, bytes, receipt, PUBLIC_REFERENCE_COMMIT), /Untrusted candidate/);
  assert.deepEqual(parseArgs(['--handoff','a.json','--tarball','b.tgz','--reference-commit',PUBLIC_REFERENCE_COMMIT]),
    {'--handoff':'a.json','--tarball':'b.tgz','--reference-commit':PUBLIC_REFERENCE_COMMIT});
  assert.throws(() => parseArgs(['--handoff','a.json','--handoff','b.json','--tarball','b.tgz']), /Usage/);
  assert.throws(() => parseArgs(['--handoff','a.json','--tarball','b.tgz']), /required/);
});
