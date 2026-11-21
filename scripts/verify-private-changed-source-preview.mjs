#!/usr/bin/env node
/**
 * Independent public npm *preview* projection of one changed Feedback source.
 * The separately authenticated, exact private-source GitHub/CI evidence and
 * exact source assembly verification remain mandatory workflow prerequisites.
 * No publication or source-authority grant is ever inferred from this file.
 */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const COMPONENTS = ['core', 'deployment', 'authentication', 'feedback', 'release-notes'];
const PKG_NAME = '@mriekki/project-forge';
const PREVIEW_VERSION = '4.36.0-preview.2';
const DOC_SOURCE = 'docs/PROJECT_INTEGRATION.md';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function requireThat(value, reason) {
  if (!value) throw new Error(reason);
}

function exactKeys(value, keys, reason) {
  requireThat(value && typeof value === 'object' && !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort()), reason);
}

export function verifyChangedSourceProjection({
  selectedSourceSha, evidence, oldComponents, packageJson, metadata, assembly, changedAssetBytes
}) {
  requireThat(typeof selectedSourceSha === 'string' && SHA40.test(selectedSourceSha),
    'Exact selected Git source commit is required');
  exactKeys(evidence, [
    'schemaVersion', 'kind', 'status', 'package', 'basePackageVersion', 'sourceCommit',
    'sourceManifestSha256', 'changedComponent', 'changedMappedSourceSha256',
    'components', 'releaseAuthorized', 'sourceOwnerTransferred', 'productionAuthorized',
    'sourceIdentityAuthenticated', 'npmPublisherUnchanged'
  ], 'Source preview evidence has unknown/missing fields');
  requireThat(evidence.schemaVersion === 1 &&
    evidence.kind === 'project-forge-versioned-source-preview-evidence' &&
    evidence.status === 'untrusted-nonpublishing-preview' &&
    evidence.sourceCommit === selectedSourceSha &&
    evidence.basePackageVersion === '4.35.0' &&
    evidence.changedComponent === 'feedback' &&
    evidence.releaseAuthorized === false &&
    evidence.sourceOwnerTransferred === false &&
    evidence.productionAuthorized === false &&
    evidence.sourceIdentityAuthenticated === false &&
    evidence.npmPublisherUnchanged === true,
  'Source preview asserted false provenance or release authority');
  requireThat(typeof evidence.sourceManifestSha256 === 'string' &&
    SHA256.test(evidence.sourceManifestSha256) &&
    typeof evidence.changedMappedSourceSha256 === 'string' &&
    SHA256.test(evidence.changedMappedSourceSha256),
  'Incomplete source digest evidence');
  exactKeys(evidence.package, ['name', 'version'], 'Preview package claim differs');
  requireThat(evidence.package.name === PKG_NAME && evidence.package.version === PREVIEW_VERSION,
    'Only reviewed changed Feedback unpublished version is accepted');
  requireThat(Buffer.isBuffer(changedAssetBytes) && changedAssetBytes.length > 0 &&
    changedAssetBytes.length <= 1024 * 1024 &&
    changedAssetBytes.toString('utf8').startsWith(
      '# GitHub Issues Feedback integration — Project-owned authorization\n'),
  'No reviewed changed Feedback asset in archive');
  const changedSha256 = crypto.createHash('sha256').update(changedAssetBytes).digest('hex');
  requireThat(changedSha256 === evidence.changedMappedSourceSha256,
    'Changed Feedback asset differs from source sidecar');

  requireThat(oldComponents?.schemaVersion === 2 &&
    oldComponents.package === PKG_NAME && oldComponents.version === '4.35.0',
  'Current Platform historical component baseline is not 4.35.0');
  requireThat(packageJson?.name === PKG_NAME && packageJson.version === PREVIEW_VERSION &&
    metadata?.schemaVersion === 2 && metadata.package === PKG_NAME &&
    metadata.version === PREVIEW_VERSION &&
    assembly?.schemaVersion === 2 && assembly.package === PKG_NAME &&
    assembly.version === PREVIEW_VERSION,
  'Archive package identity/version mismatches the exact source preview');
  for (const record of [oldComponents.components, metadata.components,
                        assembly.components, evidence.components]) {
    exactKeys(record, COMPONENTS, 'Incomplete component identity set');
  }

  for (const cid of COMPONENTS) {
    const oldValue = oldComponents.components[cid];
    const nextValue = metadata.components[cid];
    const proof = assembly.components[cid];
    const claim = evidence.components[cid];
    exactKeys(claim, ['revision', 'revisionKind', 'mappedInputSha256'],
      'Unrecognized component source-provenance contract');
    requireThat(typeof claim.mappedInputSha256 === 'string' &&
      SHA256.test(claim.mappedInputSha256),
    'Missing exact mapped consumer-input digest');
    const expectedRevision = cid === 'feedback' ? selectedSourceSha : oldValue.revision;
    const expectedKind = cid === 'feedback'
      ? 'private-monorepo-git-commit' : 'original-owner-git-commit';
    requireThat(typeof expectedRevision === 'string' && SHA40.test(expectedRevision) &&
      nextValue.revision === expectedRevision &&
      proof.revision === expectedRevision &&
      claim.revision === expectedRevision &&
      claim.revisionKind === expectedKind,
    'Mixed, invented or churned component revision identity');
    const reconstructed = structuredClone(nextValue);
    reconstructed.revision = oldValue.revision;
    assert.deepStrictEqual(reconstructed, oldValue,
      'Unexpected public component descriptor change outside Feedback revision');
  }
  requireThat(oldComponents.components.feedback.revision !== selectedSourceSha,
    'Changed Feedback version did not introduce a distinct Git source commit');

  const selected = assembly.components.feedback;
  requireThat(Array.isArray(selected.files), 'Missing Feedback assembly records');
  const mapped = selected.files.filter(record => record?.source === DOC_SOURCE);
  requireThat(mapped.length === 1 && mapped[0].sha256 === changedSha256 &&
    typeof mapped[0].destination === 'string',
  'Changed Feedback asset hash/mapping missing from packaged assembly');

  return Object.freeze({
    schemaVersion: 1,
    kind: 'project-forge-independent-changed-source-projection',
    result: 'UNPUBLISHED_PACKAGE_AND_COMPONENT_IDENTITIES_MATCH',
    version: PREVIEW_VERSION,
    sourceCommit: selectedSourceSha,
    unchangedComponentsPreserved: 4,
    changedComponent: 'feedback',
    sourceEvidenceAuthenticatedHere: false,
    releaseAuthorized: false,
    sourceOwnershipTransferred: false,
    productionAuthorized: false
  });
}

function parseArgs(argv) {
  const args = {};
  const keys = ['--archive', '--evidence', '--source-sha'];
  for (let i = 0; i < argv.length; i += 2) {
    requireThat(keys.includes(argv[i]) && !Object.hasOwn(args, argv[i]) &&
      typeof argv[i + 1] === 'string' && !argv[i + 1].startsWith('--'),
    'Invalid changed source verifier arguments');
    args[argv[i]] = argv[i + 1];
  }
  requireThat(Object.keys(args).length === keys.length, 'All exact verifier arguments required');
  return args;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const args = parseArgs(process.argv.slice(2));
    const archive = path.resolve(args['--archive']);
    const evidenceFile = path.resolve(args['--evidence']);
    const archiveStat = fs.lstatSync(archive);
    const evidenceStat = fs.lstatSync(evidenceFile);
    requireThat(archiveStat.isFile() && !archiveStat.isSymbolicLink() &&
      archiveStat.size > 0 && archiveStat.size <= 32 * 1024 * 1024,
    'Invalid changed source preview archive');
    requireThat(evidenceStat.isFile() && !evidenceStat.isSymbolicLink() &&
      evidenceStat.size > 0 && evidenceStat.size <= 1024 * 1024,
    'Invalid source evidence sidecar');
    const oldComponents = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/components.json'), 'utf8'));
    const evidence = JSON.parse(fs.readFileSync(evidenceFile, 'utf8'));
    const archiveEntry = file => execFileSync('tar', ['-xOzf', archive, 'package/' + file], {
      maxBuffer: 8 * 1024 * 1024, timeout: 15_000, stdio: ['ignore', 'pipe', 'pipe']
    });
    const asJson = name => JSON.parse(archiveEntry(name).toString('utf8'));
    const outcome = verifyChangedSourceProjection({
      selectedSourceSha: args['--source-sha'],
      evidence,
      oldComponents,
      packageJson: asJson('package.json'),
      metadata: asJson('assets/components.json'),
      assembly: asJson('assets/generated/ASSEMBLY.json'),
      changedAssetBytes: archiveEntry('assets/generated/feedback/docs/PROJECT_INTEGRATION.md')
    });
    console.log(JSON.stringify(outcome));
    console.log('INDEPENDENT UNPUBLISHED PREVIEW ONLY — no npm release or Production authorization.');
  } catch (error) {
    // Never dump private source mapping, supplied evidence or token values.
    console.error('Changed-source public preview refused: ' +
      (error instanceof Error ? error.message.slice(0, 250) : 'unknown error'));
    process.exitCode = 2;
  }
}
