/**
 * Dormant stable-contract alignment adapter for independently obtained
 * release evidence. Not a replacement for the active legacy alignment
 * command, source admission, signed-provenance verification or publisher.
 */
import { evaluateAlignment } from './check-chatgpt-contract-alignment.mjs';
import { verifyPriorRegistryArchive } from './prior-registry-archive.mjs';

export function verifyReleasedContractAlignment({
  descriptor, receiptBytes, expectedVersion, expectedSha256, archiveBytes,
  registry, platformSource, componentDigests
}) {
  const alignment = evaluateAlignment(expectedVersion, descriptor);
  if (!alignment.aligned) {
    throw new Error('Selected stable descriptor does not align with the reviewed package version');
  }
  const selectedProfile = descriptor.generation.profile;
  const proof = verifyPriorRegistryArchive({
    receiptBytes, expectedVersion, expectedSha256, archiveBytes, registry,
    platformSource, componentDigests, expectedProfile: selectedProfile
  });
  return Object.freeze({
    result: 'RELEASE_CONTRACT_EVIDENCE_MATCH',
    packageVersion: proof.previous.version,
    receiptSha256: proof.previous.receiptSha256,
    contractVersion: descriptor.contractVersion,
    selectedProfile,
    archiveReceiptMatched: proof.archiveReceiptMatched,
    registryIntegrityMatched: proof.registryIntegrityMatched,
    descriptorSelectionMatched: true,
    descriptorDocumentsVerifiedHere: false,
    receiptAuthenticatedHere: false,
    sourceEvidenceAuthenticatedHere: false,
    signatureVerifiedHere: false,
    alignmentAuthorized: false,
    releaseAuthorized: false,
    sourceOwnershipTransferred: false,
    productionAuthorized: false
  });
}
