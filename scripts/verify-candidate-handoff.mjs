#!/usr/bin/env node
// Read-only comparison against an existing durable public release receipt.
// Not a source-identity credential, npm publication gate, or Sigstore verification.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadReleaseReceipt, validateReleaseReceipt } from './release-receipt.mjs';

const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const COMPONENTS = ['core', 'deployment', 'authentication', 'feedback', 'release-notes'];

function exactObject(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...keys].sort())) {
    throw new Error(label + ' must contain exactly its approved fields');
  }
  return value;
}

function expect(value, message) {
  if (!value) throw new Error(message);
}

/**
 * Compares an untrusted candidate to a separately supplied known release receipt.
 * This function is an integrity comparison only. It does NOT verify provenance
 * signatures, establish GitHub source identity, or authorize new publication.
 */
export function verifyCandidateHandoff(claim, archiveBytes, receipt, expectedReferenceCommit) {
  exactObject(claim, [
    'schemaVersion', 'kind', 'status', 'package', 'artifact', 'components',
    'reference', 'releaseAuthorized', 'productionAuthorized', 'identityTrust'
  ], 'candidate handoff');
  expect(claim.schemaVersion === 1 &&
    claim.kind === 'project-forge-npm-candidate-handoff' &&
    claim.status === 'verification-only' &&
    claim.releaseAuthorized === false &&
    claim.productionAuthorized === false &&
    claim.identityTrust === 'not-established',
  'Untrusted candidate must never assert identity, release or Production authorization');

  const old = validateReleaseReceipt(receipt);
  const pkg = exactObject(claim.package, ['name', 'version'], 'candidate package');
  expect(pkg.name === '@mriekki/project-forge' &&
    pkg.name === old.package.name && pkg.version === old.package.version,
  'Candidate package differs from durable public release receipt');

  const artifact = exactObject(claim.artifact, ['filename', 'sha256', 'sizeBytes'], 'candidate artifact');
  expect(Buffer.isBuffer(archiveBytes) && archiveBytes.length > 0 &&
    archiveBytes.length <= 32 * 1024 * 1024,
  'Invalid candidate archive size');
  const actualHash = crypto.createHash('sha256').update(archiveBytes).digest('hex');
  expect(SHA256.test(artifact.sha256) && artifact.sha256 === actualHash &&
    artifact.sha256 === old.artifact.releaseCandidateSha256 &&
    artifact.sizeBytes === archiveBytes.length,
  'Candidate archive SHA-256/size differs from durable public release receipt');
  expect(artifact.filename === 'mriekki-project-forge-' + pkg.version + '.tgz',
    'Candidate archive filename differs from exact npm package identity');

  const expected = exactObject(claim.reference, ['platformCommit', 'tarballSha256'], 'reference');
  expect(SHA40.test(expectedReferenceCommit) &&
    expected.platformCommit === expectedReferenceCommit &&
    expected.tarballSha256 === old.artifact.releaseCandidateSha256,
  'Candidate reference does not match independently selected public reference');

  const claimedComponents = exactObject(claim.components, COMPONENTS, 'candidate components');
  const receiptComponents = exactObject(old.components, COMPONENTS, 'published components');
  for (const id of COMPONENTS) {
    const keys = id === 'core' ? ['revision', 'version'] : ['revision'];
    const candidate = exactObject(claimedComponents[id], keys, 'candidate ' + id);
    const published = exactObject(receiptComponents[id], keys, 'published ' + id);
    expect(SHA40.test(candidate.revision) &&
      JSON.stringify(candidate) === JSON.stringify(published),
    'Candidate ' + id + ' revision differs from public receipt');
  }
  return Object.freeze({
    package: pkg.name,
    version: pkg.version,
    archiveSha256: actualHash,
    result: 'MATCHES_EXISTING_PUBLIC_RELEASE',
    identityVerified: false,
    publicationAuthorized: false,
    productionAuthorized: false
  });
}

export function parseArgs(args) {
  const result = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!['--handoff', '--tarball', '--reference-commit'].includes(arg) ||
      Object.hasOwn(result, arg) || !args[index + 1] || args[index + 1].startsWith('--')) {
      throw new Error('Usage: --handoff PATH --tarball PATH --reference-commit EXACT_PUBLIC_SHA');
    }
    result[arg] = args[++index];
  }
  if (Object.keys(result).length !== 3) {
    throw new Error('All three candidate verification inputs are required');
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const args = parseArgs(process.argv.slice(2));
    const handoff = JSON.parse(fs.readFileSync(args['--handoff'], 'utf8'));
    // Reads the committed receipt under THIS public Platform checkout, not an
    // arbitrary caller-supplied JSON file or an untrusted private worktree.
    const receipt = await loadReleaseReceipt(handoff?.package?.version);
    const bytes = fs.readFileSync(args['--tarball']);
    const outcome = verifyCandidateHandoff(handoff, bytes, receipt, args['--reference-commit']);
    console.log(JSON.stringify(outcome));
    console.log('Candidate matches a known published public archive; new-release trust NOT established.');
  } catch (error) {
    console.error('Public candidate verification rejected: ' + error.message);
    process.exitCode = 2;
  }
}
