/**
 * Offline native stable candidate verification. The inputs must come from
 * the protected source/CI/registry admission path. This module compares
 * evidence; it does not confer publication or source-ownership authority.
 */
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { validateNativeIntent, verifyNativeIntent } from './native-source-receipt.mjs';
import { readReleaseArchiveProjection, verifyPriorRegistryArchive } from './prior-registry-archive.mjs';

const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const requireFact = (value, message) => { if (!value) throw new Error(message); };
function exactFields(value, keys, label) {
  requireFact(value && typeof value === 'object' && !Array.isArray(value) &&
    isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort()),
    'Invalid ' + label);
}

export function verifyNativeStableCandidate({intent, prior, candidateArchiveBytes, observedSource}) {
  validateNativeIntent(intent);
  exactFields(prior, ['receiptBytes','archiveBytes','registry','platformSource','componentDigests'],
    'prior archive evidence');
  exactFields(observedSource, ['platformSource','sourceCommit','manifestSha256','qualificationEvent',
    'nativeSourceMain','platformMain','componentDigests'], 'independent source observations');
  const previous = verifyPriorRegistryArchive({
    ...prior, expectedVersion: intent.source.previousVersion,
    expectedSha256: intent.source.previousReceiptSha256
  }).previous;
  requireFact(Buffer.isBuffer(candidateArchiveBytes) && candidateArchiveBytes.length > 0 &&
    candidateArchiveBytes.length <= 32 * 1024 * 1024, 'Invalid candidate archive size');
  const candidateSha256 = sha256(candidateArchiveBytes);
  requireFact(candidateSha256 === intent.candidateSha256, 'Candidate archive digest differs from intent');
  const projection = readReleaseArchiveProjection({
    archiveBytes: candidateArchiveBytes, expectedVersion: intent.package.version,
    requirePublishableForm: true
  });
  const observed = {
    ...observedSource,
    packageVersion: projection.package.version,
    packageComponents: projection.packageComponents,
    assemblyRevisions: projection.assemblyRevisions,
    candidateSha256
  };
  const result = verifyNativeIntent({intent, previous, observed});
  return Object.freeze({
    ...result,
    result: 'NATIVE_STABLE_CANDIDATE_EVIDENCE_MATCH',
    candidateSha256,
    priorArchiveReceiptMatched: true,
    candidateArchiveMatched: true,
    priorReceiptAuthenticatedHere: false,
    registrySignatureVerifiedHere: false,
    publicationAuthorized: false
  });
}
