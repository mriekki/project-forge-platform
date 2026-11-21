/**
 * Dormant v2 native-source receipt contract.
 *
 * A structural parser/constructor and comparison of independently observed
 * facts. This module is NOT the existing publication/receipt/descriptor path,
 * does not authenticate claims, access a registry, or authorize writes.
 */
import { isDeepStrictEqual } from 'node:util';
const PKG = '@mriekki/project-forge';
const COMPONENTS = ['authentication', 'core', 'deployment', 'feedback', 'release-notes'];
const ORIGINAL = 'original-owner-git-commit';
const NATIVE = 'private-monorepo-git-commit';
const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const SIGSTORE = /^https:\/\/search\.sigstore\.dev\/\?logIndex=[0-9]+$/;
const EVENTS = new Set(['workflow_dispatch', 'issues']);
const obj = x => x !== null && typeof x === 'object' && !Array.isArray(x);
function check(x, message) {
  if (!x) throw new Error(message);
}
function fields(x, names, label) {
  check(obj(x) && isDeepStrictEqual(Object.keys(x).sort(), [...names].sort()),
    'Invalid or unknown ' + label + ' fields');
}
const exact = (x, p) => typeof x === 'string' && p.test(x);
const positive = x => Number.isSafeInteger(x) && x > 0;

function version(x) {
  check(exact(x, SEMVER), 'An exact stable version is required');
  return x.split('.').map(BigInt);
}
function advances(a, b) {
  const x = version(a), y = version(b);
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i];
  return false;
}
function componentRecords(records) {
  fields(records, COMPONENTS, 'component inventory');
  for (const cid of COMPONENTS) {
    const x = records[cid];
    fields(x, cid === 'core'
      ? ['revision', 'revisionKind', 'mappedInputSha256', 'version']
      : ['revision', 'revisionKind', 'mappedInputSha256'], 'component');
    check(exact(x.revision, SHA40) && [ORIGINAL, NATIVE].includes(x.revisionKind) &&
      exact(x.mappedInputSha256, SHA256), 'Invalid component revision kind or digest');
    if (cid === 'core') version(x.version);
  }
}
function artifact(x) {
  fields(x, ['releaseCandidateSha256', 'registryShasum'], 'artifact');
  check(exact(x.releaseCandidateSha256, SHA256) && exact(x.registryShasum, SHA40),
    'Invalid artifact identity');
}
function publication(x) {
  fields(x, ['publishedAt', 'workflowRunId', 'publisher', 'registryIdentity',
    'neutralNpxSmoke', 'provenance'], 'publication');
  check(exact(x.publishedAt, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/) &&
    !Number.isNaN(Date.parse(x.publishedAt)) &&
    new Date(x.publishedAt).toISOString().replace('.000Z','Z') === x.publishedAt &&
    positive(x.workflowRunId) && x.publisher === 'github-oidc' &&
    x.registryIdentity === 'verified' && x.neutralNpxSmoke === 'verified',
  'Incomplete publication verification');
  fields(x.provenance, ['signed', 'transparencyLogUrl'], 'signed provenance');
  check(x.provenance.signed === true && exact(x.provenance.transparencyLogUrl, SIGSTORE),
    'Incomplete signed public provenance');
}
function ciEvidence(x) {
  fields(x, ['result', 'workflowRunId', 'runAttempt'], 'CI evidence');
  check(x.result === 'success' && positive(x.workflowRunId) && positive(x.runAttempt),
    'Successful exact-run CI evidence required');
}

function validateReleaseIdentity(receipt, expectedVersion) {
  fields(receipt.package, ['name','version'], 'package');
  check(receipt.package.name === PKG, 'Wrong package');
  version(receipt.package.version);
  check(expectedVersion === undefined || expectedVersion === receipt.package.version,
    'Receipt version differs from selection');
  check(exact(receipt.platformSource, SHA40), 'Exact public Platform source required');
  fields(receipt.source, ['mode','commit','previousVersion','manifestSha256',
    'qualificationEvent','previousReceiptSha256'], 'native source');
  check(receipt.source.mode === 'native-monorepo' && exact(receipt.source.commit, SHA40) &&
    exact(receipt.source.manifestSha256, SHA256) &&
    exact(receipt.source.previousReceiptSha256, SHA256) &&
    EVENTS.has(receipt.source.qualificationEvent), 'Invalid native source identity');
  check(advances(receipt.package.version, receipt.source.previousVersion),
    'Release version must advance previous accepted version');
  componentRecords(receipt.components);
  fields(receipt.ci, ['nativeSourceMain','platformMain'], 'native CI');
  ciEvidence(receipt.ci.nativeSourceMain);
  ciEvidence(receipt.ci.platformMain);
}

export function validateNativeReceipt(receipt, expectedVersion) {
  fields(receipt, ['schemaVersion','kind','package','platformSource','source','components',
    'artifact','publication','ci'], 'native receipt');
  check(receipt.schemaVersion === 2 && receipt.kind === 'project-forge-native-source-release',
    'Unsupported native receipt schema or kind');
  validateReleaseIdentity(receipt, expectedVersion);
  artifact(receipt.artifact);
  publication(receipt.publication);
  return receipt;
}

// Explicit construction from a complete fact record, not a signing or
// publication API. Never use arbitrary preview metadata as verified facts.
export function constructNativeReceipt(facts) {
  fields(facts, ['package','platformSource','source','components','artifact','publication','ci'],
    'native fact record');
  return validateNativeReceipt({
    schemaVersion: 2, kind: 'project-forge-native-source-release', ...structuredClone(facts)
  });
}

// The caller must obtain all observed values independently, verify exact main,
// actor/code/job/step policy, and verify the actual archive and registry proof.
// The function deliberately reports comparison only, not authentication.
function compareReleaseProjection(receipt, previous, observed) {
  fields(previous, ['version','receiptSha256','components'], 'previous acceptance projection');
  componentRecords(previous.components);
  check(previous.version === receipt.source.previousVersion &&
    previous.receiptSha256 === receipt.source.previousReceiptSha256,
    'Previous accepted version or receipt digest differs');
  check(observed.packageVersion === receipt.package.version &&
    observed.platformSource === receipt.platformSource &&
    observed.sourceCommit === receipt.source.commit &&
    observed.manifestSha256 === receipt.source.manifestSha256 &&
    observed.qualificationEvent === receipt.source.qualificationEvent &&
    isDeepStrictEqual(observed.nativeSourceMain, receipt.ci.nativeSourceMain) &&
    isDeepStrictEqual(observed.platformMain, receipt.ci.platformMain),
  'Exact selected source, qualification or public CI differs');
  fields(observed.componentDigests, COMPONENTS, 'observed mapped inputs');
  fields(observed.packageComponents, COMPONENTS, 'observed package components');
  fields(observed.assemblyRevisions, COMPONENTS, 'observed assembly revisions');
  let changed = 0;
  for (const cid of COMPONENTS) {
    const old = previous.components[cid], next = receipt.components[cid];
    const digest = observed.componentDigests[cid];
    check(exact(digest, SHA256) && next.mappedInputSha256 === digest,
      'Mapped input digest differs from independent observation');
    const expected = digest === old.mappedInputSha256 ? old : {
      ...next, revision: receipt.source.commit, revisionKind: NATIVE
    };
    if (digest !== old.mappedInputSha256) {
      changed++;
      check(next.revision !== old.revision,
        'Changed mapped inputs require a distinct native commit');
    }
    check(isDeepStrictEqual(next, expected), 'Component identity continuity mismatch');
    const projection = cid === 'core'
      ? {revision: next.revision, version: next.version} : {revision: next.revision};
    check(isDeepStrictEqual(observed.packageComponents[cid], projection) &&
      observed.assemblyRevisions[cid] === next.revision,
    'Public package/assembly revision projection differs');
  }
  return changed;
}

export function verifyNativeProjection({ receipt, previous, observed }) {
  validateNativeReceipt(receipt);
  fields(observed, ['packageVersion','platformSource','sourceCommit','manifestSha256',
    'qualificationEvent','nativeSourceMain','platformMain','componentDigests',
    'packageComponents','assemblyRevisions','artifact','publication'], 'observed proof');
  const changed = compareReleaseProjection(receipt, previous, observed);
  check(isDeepStrictEqual(receipt.artifact, observed.artifact) &&
    isDeepStrictEqual(receipt.publication, observed.publication),
  'Independent artifact or publication evidence differs');
  return Object.freeze({result:'NATIVE_PROJECTION_MATCH', changedComponents:changed,
    sourceEvidenceAuthenticatedHere:false, releaseAuthorized:false, productionAuthorized:false,
    sourceOwnershipTransferred:false});
}

// Read-only recovery classification; a lookup failure is NOT registry absence.
// Recheck actual registry proof, signed provenance and full receipt projection
// before an authorized recovery action. This never returns permission to publish.
export function classifyNativeRecovery({expectedReceipt, registry, existingReceipt}) {
  validateNativeReceipt(expectedReceipt);
  fields(registry, registry?.status === 'present'
    ? ['status','package','artifact'] : ['status'], 'registry observation');
  let decision;
  if (registry.status === 'unknown') decision = 'BLOCKED_REGISTRY_UNVERIFIED';
  else if (registry.status === 'absent') {
    decision = existingReceipt === null
      ? 'NOT_PUBLISHED_NEW_AUTHORIZATION_REQUIRED' : 'BLOCKED_RECEIPT_WITHOUT_REGISTRY';
  } else {
    check(registry.status === 'present', 'Unknown registry status');
    fields(registry.package, ['name','version'], 'registry package');
    artifact(registry.artifact);
    if (!isDeepStrictEqual(registry.package, expectedReceipt.package) ||
        !isDeepStrictEqual(registry.artifact, expectedReceipt.artifact)) {
      decision = 'BLOCKED_REGISTRY_CONFLICT';
    } else if (existingReceipt === null) {
      decision = 'VERIFY_EXISTING_PUBLICATION_NO_REPUBLISH';
    } else {
      validateNativeReceipt(existingReceipt);
      decision = isDeepStrictEqual(existingReceipt, expectedReceipt)
        ? 'MATCHED_RECEIPT_VERIFY_ALIGNMENT' : 'BLOCKED_RECEIPT_CONFLICT';
    }
  }
  return Object.freeze({decision, publishAuthorized:false, receiptWriteAuthorized:false,
    alignmentAuthorized:false});
}


// Separate prepublication identity from postpublication facts. An intent
// intentionally contains no purported registry success or signature.
export function validateNativeIntent(intent) {
  fields(intent, ['schemaVersion','kind','package','platformSource','source',
    'components','ci','candidateSha256','releaseAuthorized','sourceOwnershipTransferred',
    'productionAuthorized'], 'native release intent');
  check(intent.schemaVersion === 1 && intent.kind === 'project-forge-native-release-intent' &&
    intent.releaseAuthorized === false && intent.sourceOwnershipTransferred === false &&
    intent.productionAuthorized === false, 'Invalid nonauthorizing native intent');
  validateReleaseIdentity(intent);
  check(exact(intent.candidateSha256, SHA256), 'Exact candidate archive digest required');
  return intent;
}
export function constructNativeIntent(facts) {
  fields(facts, ['package','platformSource','source','components','ci','candidateSha256'],
    'native intent facts');
  return validateNativeIntent({ schemaVersion:1, kind:'project-forge-native-release-intent',
    ...structuredClone(facts), releaseAuthorized:false, sourceOwnershipTransferred:false,
    productionAuthorized:false });
}
export function verifyNativeIntent({intent, previous, observed}) {
  validateNativeIntent(intent);
  fields(observed, ['packageVersion','platformSource','sourceCommit','manifestSha256',
    'qualificationEvent','nativeSourceMain','platformMain','componentDigests',
    'packageComponents','assemblyRevisions','candidateSha256'], 'observed intent proof');
  const changed = compareReleaseProjection(intent, previous, observed);
  check(observed.candidateSha256 === intent.candidateSha256, 'Candidate digest differs');
  return Object.freeze({result:'NATIVE_INTENT_MATCH',changedComponents:changed,
    sourceEvidenceAuthenticatedHere:false,releaseAuthorized:false,
    sourceOwnershipTransferred:false,productionAuthorized:false});
}
export function verifyReceiptMatchesIntent(receipt, intent) {
  validateNativeReceipt(receipt);
  validateNativeIntent(intent);
  for (const field of ['package','platformSource','source','components','ci']) {
    check(isDeepStrictEqual(receipt[field], intent[field]), 'Receipt differs from selected intent');
  }
  check(receipt.artifact.releaseCandidateSha256 === intent.candidateSha256,
    'Receipt archive differs from selected intent');
  return receipt;
}
// Use only AFTER independent verification of registry and signed publication
// facts. Construction remains a structural operation, not a publication claim.
export function constructNativeReceiptFromIntent(intent, facts) {
  validateNativeIntent(intent);
  fields(facts, ['artifact','publication'], 'postpublication facts');
  const {package:packageInfo,platformSource,source,components,ci} = intent;
  return verifyReceiptMatchesIntent(constructNativeReceipt({
    package:packageInfo,platformSource,source,components,ci,...facts
  }), intent);
}

// Resume from exact accepted intent and separately observed registry state.
// Unlike the postpublication recovery comparison, this requires no fictional
// publication timestamp, workflow or signature to exist before publishing.
export function classifyNativeIntentRecovery({intent, registry, existingReceipt}) {
  validateNativeIntent(intent);
  fields(registry, registry?.status === 'present'
    ? ['status','package','artifact'] : ['status'], 'registry observation');
  let decision;
  if (registry.status === 'unknown') decision = 'BLOCKED_REGISTRY_UNVERIFIED';
  else if (registry.status === 'absent') decision = existingReceipt === null
    ? 'NOT_PUBLISHED_NEW_AUTHORIZATION_REQUIRED' : 'BLOCKED_RECEIPT_WITHOUT_REGISTRY';
  else {
    check(registry.status === 'present', 'Unknown registry status');
    fields(registry.package, ['name','version'], 'registry package');
    artifact(registry.artifact);
    if (!isDeepStrictEqual(registry.package,intent.package) ||
        registry.artifact.releaseCandidateSha256 !== intent.candidateSha256) {
      decision = 'BLOCKED_REGISTRY_CONFLICT';
    } else if (existingReceipt === null) {
      decision = 'VERIFY_EXISTING_PUBLICATION_NO_REPUBLISH';
    } else {
      try {
        verifyReceiptMatchesIntent(existingReceipt,intent);
        check(isDeepStrictEqual(registry.artifact,existingReceipt.artifact),
          'Registry and receipt artifact mismatch');
        decision = 'MATCHED_RECEIPT_VERIFY_ALIGNMENT';
      } catch {
        decision = 'BLOCKED_RECEIPT_CONFLICT';
      }
    }
  }
  return Object.freeze({decision,publishAuthorized:false,receiptWriteAuthorized:false,
    alignmentAuthorized:false});
}
