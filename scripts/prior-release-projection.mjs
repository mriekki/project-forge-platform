/**
 * Dormant version-aware previous-release bridge.
 *
 * Receipt bytes and expectations MUST be obtained from independently
 * authenticated public release history and reviewed intent. This is not a
 * network/registry/signature verifier, and is not wired into live publishing.
 */
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { validateReleaseReceipt } from './release-receipt.mjs';
import { validateNativeReceipt, validateNativeIntent, verifyNativeIntent }
  from './native-source-receipt.mjs';

const COMPONENTS = ['authentication','core','deployment','feedback','release-notes'];
const SHA256 = /^[0-9a-f]{64}$/;
const SHA40 = /^[0-9a-f]{40}$/;
const STABLE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const exact = (v, p) => typeof v === 'string' && p.test(v);
function requireFact(value, message) {
  if (!value) throw new Error(message);
}
function keys(value, names, label) {
  requireFact(value && typeof value === 'object' && !Array.isArray(value) &&
    isDeepStrictEqual(Object.keys(value).sort(), [...names].sort()), 'Invalid ' + label);
}

export function selectPriorRelease({receiptBytes, expectedVersion, expectedSha256, observed}) {
  requireFact(Buffer.isBuffer(receiptBytes) && receiptBytes.length > 0 &&
    receiptBytes.length <= 1024 * 1024, 'Expected bounded exact receipt bytes');
  requireFact(exact(expectedVersion, STABLE) && exact(expectedSha256, SHA256),
    'Expected exact prior version and receipt digest');
  const actual = createHash('sha256').update(receiptBytes).digest('hex');
  requireFact(actual === expectedSha256, 'Prior receipt digest mismatch');
  // Fatal UTF-8 decode prevents substitution of malformed bytes.
  let receipt;
  try {
    receipt = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(receiptBytes));
  } catch {
    throw new Error('Malformed prior receipt');
  }
  requireFact(receipt && typeof receipt === 'object' && !Array.isArray(receipt),
    'Malformed prior receipt');
  if (receipt.schemaVersion === 1) validateReleaseReceipt(receipt, expectedVersion);
  else if (receipt.schemaVersion === 2) validateNativeReceipt(receipt, expectedVersion);
  else throw new Error('Unsupported prior receipt schema');
  keys(observed, ['package','platformSource','artifact','packageComponents','componentDigests'],
    'independent prior release observations');
  requireFact(isDeepStrictEqual(observed.package, receipt.package) &&
    exact(observed.platformSource, SHA40) && observed.platformSource === receipt.platformSource &&
    isDeepStrictEqual(observed.artifact, receipt.artifact),
    'Prior package/source/archive proof differs');
  keys(receipt.components, COMPONENTS, 'five-component prior receipt');
  keys(observed.packageComponents, COMPONENTS, 'prior package component observations');
  keys(observed.componentDigests, COMPONENTS, 'prior mapped-input observations');
  const components = {};
  for (const cid of COMPONENTS) {
    const original = receipt.components[cid];
    const projection = cid === 'core'
      ? {revision:original.revision, version:original.version} : {revision:original.revision};
    requireFact(isDeepStrictEqual(observed.packageComponents[cid],projection),
      'Prior package compatibility projection differs');
    const digest = observed.componentDigests[cid];
    requireFact(exact(digest,SHA256), 'Invalid independently computed prior mapped digest');
    if (receipt.schemaVersion === 1) {
      // Legacy receipt cannot attest to a mapped-input digest. The caller
      // must recompute it against the exact original-owner source evidence.
      // Restrict the first native migration to the accepted five-component
      // historical parity baseline; older shapes stay in the legacy reader.
      requireFact(expectedVersion === '4.35.0', 'Unsupported legacy native migration baseline');
      components[cid] = {...projection, revisionKind:'original-owner-git-commit', mappedInputSha256:digest};
    } else {
      requireFact(original.mappedInputSha256 === digest, 'Prior native mapped digest differs');
      components[cid] = structuredClone(original);
    }
  }
  // No unrecognized receipt data crosses this deliberately small projection.
  return {version:expectedVersion,receiptSha256:actual,components};
}

export function verifyIntentWithPriorReceipt({intent,receiptBytes,priorObserved,candidateObserved}) {
  validateNativeIntent(intent);
  const previous = selectPriorRelease({
    receiptBytes, expectedVersion:intent.source.previousVersion,
    expectedSha256:intent.source.previousReceiptSha256, observed:priorObserved
  });
  const result = verifyNativeIntent({intent,previous,observed:candidateObserved});
  return Object.freeze({...result, priorReceiptBytesMatched:true,
    priorReceiptAuthenticatedHere:false});
}
