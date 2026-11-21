/**
 * Offline comparison of an already retrieved exact registry archive against
 * reviewed receipt bytes. The caller owns authenticated transport, source
 * identity, signature verification, and independently recomputed source
 * digests. No registry, publication or authorization operation occurs here.
 */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { isDeepStrictEqual } from 'node:util';
import { selectPriorRelease } from './prior-release-projection.mjs';
import { validateReleaseReceipt } from './release-receipt.mjs';
import { validateNativeReceipt } from './native-source-receipt.mjs';

const PKG = '@mriekki/project-forge';
const COMPONENTS = ['authentication','core','deployment','feedback','release-notes'];
const hash = (algorithm, bytes, encoding = 'hex') =>
  createHash(algorithm).update(bytes).digest(encoding);
function requireFact(value, reason) {
  if (!value) throw new Error(reason);
}
function inventory(value) {
  requireFact(value && typeof value === 'object' && !Array.isArray(value) &&
    isDeepStrictEqual(Object.keys(value).sort(), COMPONENTS), 'Incomplete archive component inventory');
}
function archiveJson(bytes, name) {
  try {
    // Read only the identified entry, never extract to a filesystem.
    const data = execFileSync('tar', ['-xOzf', '-', 'package/' + name], {
      input: bytes, timeout: 15000, maxBuffer: 8 * 1024 * 1024,
      stdio: ['pipe','pipe','pipe']
    });
    return JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(data));
  } catch {
    throw new Error('Unable to read exact npm archive metadata');
  }
}

// Shared exact archive projection. Only the independent caller can establish
// that these bytes were rebuilt from the reviewed, authenticated source.
export function readReleaseArchiveProjection({archiveBytes, expectedVersion, expectedProfile,
  requirePublishableForm = false}) {
  requireFact(Buffer.isBuffer(archiveBytes) && archiveBytes.length > 0 &&
    archiveBytes.length <= 32 * 1024 * 1024, 'Invalid release archive size');
  const pkg = archiveJson(archiveBytes, 'package.json');
  const metadata = archiveJson(archiveBytes, 'assets/components.json');
  const assembly = archiveJson(archiveBytes, 'assets/generated/ASSEMBLY.json');
  requireFact(pkg?.name === PKG && pkg?.version === expectedVersion && pkg?.private !== true &&
    metadata?.schemaVersion === 2 && metadata?.package === PKG && metadata?.version === expectedVersion &&
    assembly?.schemaVersion === 2 && assembly?.package === PKG && assembly?.version === expectedVersion,
    'Prior archive package metadata differs');
  if (requirePublishableForm) {
    requireFact((pkg.private === undefined || pkg.private === false) &&
      pkg.publishConfig?.access === 'public' && pkg.publishConfig?.provenance === true,
      'Candidate is not in public stable release form');
  }
  inventory(metadata.components);
  inventory(assembly.components);
  // Optional descriptor alignment uses profiles read from the same verified
  // archive, not from the potentially stale checkout or a caller projection.
  if (expectedProfile !== undefined) {
    requireFact(typeof expectedProfile === 'string' &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(expectedProfile) &&
      metadata.profiles && typeof metadata.profiles === 'object' &&
      !Array.isArray(metadata.profiles) &&
      Object.hasOwn(metadata.profiles, expectedProfile),
      'Exact archive does not provide the selected generation profile');
    const selected = metadata.profiles[expectedProfile]?.components;
    requireFact(Array.isArray(selected) && selected.includes('core') &&
      selected.includes('deployment') && new Set(selected).size === selected.length &&
      selected.every(id => COMPONENTS.includes(id)),
      'Invalid selected archive generation profile component set');
  }
  const packageComponents = {};
  for (const id of COMPONENTS) {
    const component = metadata.components[id], assembled = assembly.components[id];
    requireFact(component && assembled && component.revision === assembled.revision &&
      (id !== 'core' || component.version === assembled.version),
      'Prior archive component revision mismatch');
    packageComponents[id] = id === 'core'
      ? {revision:component.revision,version:component.version} : {revision:component.revision};
  }
  return {package: {name:pkg.name, version:pkg.version}, packageComponents,
    assemblyRevisions: Object.fromEntries(COMPONENTS.map(id => [id, assembly.components[id].revision]))};
}

export function verifyPriorRegistryArchive({
  receiptBytes, expectedVersion, expectedSha256, archiveBytes,
  registry, platformSource, componentDigests, expectedProfile
}) {
  requireFact(Buffer.isBuffer(receiptBytes) && receiptBytes.length > 0 &&
    receiptBytes.length <= 1024 * 1024 &&
    hash('sha256', receiptBytes) === expectedSha256, 'Prior receipt digest mismatch');
  let receipt;
  try {
    receipt = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(receiptBytes));
  } catch {
    throw new Error('Malformed prior receipt');
  }
  if (receipt?.schemaVersion === 1) validateReleaseReceipt(receipt, expectedVersion);
  else if (receipt?.schemaVersion === 2) validateNativeReceipt(receipt, expectedVersion);
  else throw new Error('Unsupported prior receipt schema');

  requireFact(Buffer.isBuffer(archiveBytes) && archiveBytes.length > 0 &&
    archiveBytes.length <= 32 * 1024 * 1024, 'Invalid prior archive size');
  const artifact = {
    releaseCandidateSha256: hash('sha256', archiveBytes),
    registryShasum: hash('sha1', archiveBytes)
  };
  requireFact(isDeepStrictEqual(artifact, receipt.artifact), 'Prior archive differs from receipt');
  requireFact(registry?.name === PKG && registry?.version === expectedVersion &&
    registry?.dist?.shasum === artifact.registryShasum &&
    registry?.dist?.integrity === 'sha512-' + hash('sha512', archiveBytes, 'base64'),
    'Exact registry version or integrity differs');

  const {package: packageInfo, packageComponents} = readReleaseArchiveProjection({
    archiveBytes, expectedVersion, expectedProfile
  });
  const observed = {package:packageInfo, platformSource,
    artifact, packageComponents, componentDigests};
  const previous = selectPriorRelease({receiptBytes,expectedVersion,expectedSha256,observed});
  return Object.freeze({previous, observed, archiveReceiptMatched:true,
    registryIntegrityMatched:true, priorReceiptAuthenticatedHere:false,
    sourceEvidenceAuthenticatedHere:false, signatureVerifiedHere:false,
    releaseAuthorized:false, sourceOwnershipTransferred:false, productionAuthorized:false});
}
