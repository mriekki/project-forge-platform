import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';
import { verifyChangedSourceProjection } from '../scripts/verify-private-changed-source-preview.mjs';

const SOURCE = 'a'.repeat(40);
const IDS = ['core', 'deployment', 'authentication', 'feedback', 'release-notes'];
const DOC = Buffer.from('# GitHub Issues Feedback integration — Project-owned authorization\nPreview source asset.\n');
const HASH = crypto.createHash('sha256').update(DOC).digest('hex');

function fixture() {
  const old = {
    schemaVersion: 2, package: '@mriekki/project-forge', version: '4.35.0',
    components: Object.fromEntries(IDS.map((cid, i) => [cid, {
      revision: (i + 1).toString(16).repeat(40),
      distribution: 'greenfield-project', descriptor: 'assets/' + cid + '/distribution.json',
      sourceRoot: 'assets/generated/' + cid,
      canonicalDescriptor: 'distributions/greenfield-project.json',
      ...(cid === 'core' ? { version: '4.5.1' } : {})
    }]))
  };
  const metadata = structuredClone(old);
  metadata.version = '4.36.0-preview.2';
  metadata.components.feedback.revision = SOURCE;
  const assembly = {
    schemaVersion: 2, package: '@mriekki/project-forge',
    version: '4.36.0-preview.2',
    components: Object.fromEntries(IDS.map(cid => [cid, {
      revision: metadata.components[cid].revision,
      files: cid === 'feedback' ? [{
        source: 'docs/PROJECT_INTEGRATION.md',
        destination: 'tools/project-forge-feedback-kit/PROJECT_INTEGRATION.md',
        sha256: HASH
      }] : []
    }]))
  };
  const evidence = {
    schemaVersion: 1, kind: 'project-forge-versioned-source-preview-evidence',
    status: 'untrusted-nonpublishing-preview',
    package: { name: '@mriekki/project-forge', version: '4.36.0-preview.2' },
    basePackageVersion: '4.35.0', sourceCommit: SOURCE,
    sourceManifestSha256: 'b'.repeat(64),
    changedComponent: 'feedback', changedMappedSourceSha256: HASH,
    components: Object.fromEntries(IDS.map(cid => [cid, {
      revision: metadata.components[cid].revision,
      revisionKind: cid === 'feedback' ? 'private-monorepo-git-commit' : 'original-owner-git-commit',
      mappedInputSha256: 'd'.repeat(64)
    }])),
    releaseAuthorized: false, sourceOwnerTransferred: false,
    productionAuthorized: false, sourceIdentityAuthenticated: false,
    npmPublisherUnchanged: true
  };
  return {
    selectedSourceSha: SOURCE, evidence, oldComponents: old,
    packageJson: { name: '@mriekki/project-forge', version: '4.36.0-preview.2' },
    metadata, assembly, changedAssetBytes: DOC
  };
}

function rejects(mutator, expression) {
  const data = fixture();
  mutator(data);
  assert.throws(() => verifyChangedSourceProjection(data), expression);
}

test('changed Feedback source proof keeps four original owner identities and never asserts release', () => {
  const result = verifyChangedSourceProjection(fixture());
  assert.equal(result.result, 'UNPUBLISHED_PACKAGE_AND_COMPONENT_IDENTITIES_MATCH');
  assert.equal(result.unchangedComponentsPreserved, 4);
  assert.equal(result.changedComponent, 'feedback');
  assert.equal(result.releaseAuthorized, false);
  assert.equal(result.sourceEvidenceAuthenticatedHere, false);
  assert.equal(result.sourceOwnershipTransferred, false);
  assert.equal(result.productionAuthorized, false);
  assert.equal(JSON.stringify(result).includes('private-source'), false);
});

test('publication, source-owner, Production and fake authenticated-source flags are refused', () => {
  rejects(x => { x.evidence.releaseAuthorized = true; }, /false provenance or release authority/);
  rejects(x => { x.evidence.sourceOwnerTransferred = true; }, /false provenance or release authority/);
  rejects(x => { x.evidence.productionAuthorized = true; }, /false provenance or release authority/);
  rejects(x => { x.evidence.sourceIdentityAuthenticated = true; }, /false provenance or release authority/);
  rejects(x => { x.evidence.npmPublisherUnchanged = false; }, /false provenance or release authority/);
});

test('wrong selected private SHA, metadata source commit and unknown sidecar claims fail closed', () => {
  rejects(x => { x.selectedSourceSha = 'branch'; }, /Exact selected/);
  rejects(x => { x.evidence.sourceCommit = 'e'.repeat(40); }, /false provenance/);
  rejects(x => { x.evidence.privateRepository = 'private/repo'; }, /unknown\/missing fields/);
  rejects(x => { delete x.evidence.components; }, /unknown\/missing fields/);
});

test('the untrusted evidence must preserve exact revision kind and each component identity', () => {
  rejects(x => { x.evidence.components.feedback.revisionKind = 'original-owner-git-commit'; },
    /Mixed, invented or churned/);
  rejects(x => { x.evidence.components.core.revisionKind = 'private-monorepo-git-commit'; },
    /Mixed, invented or churned/);
  rejects(x => { x.evidence.components.feedback.revision = 'c'.repeat(40); },
    /Mixed, invented or churned/);
  rejects(x => { x.metadata.components.authentication.revision = SOURCE; },
    /Mixed, invented or churned/);
  rejects(x => { x.evidence.components.deployment.mappedInputSha256 = 'a'.repeat(40); },
    /mapped consumer-input digest/);
});

test('wrong preview version and unexpected component changes refuse', () => {
  rejects(x => { x.packageJson.version = '4.36.0'; }, /package identity\/version/);
  rejects(x => { x.evidence.package.version = '4.36.0'; }, /Only reviewed/);
  rejects(x => { x.metadata.components.core.version = '6.0.0'; }, /Unexpected public component descriptor/);
  rejects(x => { x.metadata.components.feedback.distribution = 'other'; }, /Unexpected public component descriptor/);
  rejects(x => { delete x.metadata.components['release-notes']; }, /Incomplete component/);
});

test('different changed file, corrupted asset and bogus assembly hash refuse', () => {
  rejects(x => { x.changedAssetBytes = Buffer.from('bad'); }, /No reviewed/);
  rejects(x => { x.changedAssetBytes = Buffer.from(DOC.toString('utf8') + 'changed'); },
    /differs from source sidecar/);
  rejects(x => { x.assembly.components.feedback.files[0].sha256 = 'f'.repeat(64); },
    /asset hash\/mapping missing/);
  rejects(x => { x.assembly.components.feedback.files = []; }, /asset hash\/mapping missing/);
});

test('candidate evidence is explicitly untrusted, not a publication receipt', () => {
  rejects(x => { x.evidence.status = 'approved'; }, /false provenance/);
  rejects(x => { x.evidence.schemaVersion = 2; }, /false provenance/);
  rejects(x => { x.evidence.changedComponent = 'core'; }, /false provenance/);
});
