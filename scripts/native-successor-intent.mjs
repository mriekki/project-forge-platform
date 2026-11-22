/**
 * Offline successor intent composition. The protected caller must independently
 * authenticate the predecessor receipt, registry signature, source Git
 * ancestry, qualification run/attempt, selection and public main CI.
 * This routine neither authenticates transport nor invokes a publisher.
 */
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {verifyPriorRegistryArchive,readReleaseArchiveProjection} from './prior-registry-archive.mjs';
import {compareSuccessorEvidence} from './verify-native-successor-evidence.mjs';
import {validateNativeReceipt,constructNativeIntent} from './native-source-receipt.mjs';
import {verifyNativeStableCandidate} from './native-stable-candidate-verifier.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const need = (ok,msg) => {if(!ok) throw new Error(msg);};
const sha = /^[0-9a-f]{40}$/;
const digest = /^[0-9a-f]{64}$/;
const exact = (x,p) => typeof x==='string' && p.test(x);
function fields(value,keys,label) {
  need(value && typeof value==='object' && !Array.isArray(value) &&
    equal(Object.keys(value).sort(),[...keys].sort()), 'Invalid '+label);
}
function archive(bytes) {
  need(Buffer.isBuffer(bytes)&&bytes.length>0&&bytes.length<=32*1024*1024,
    'Invalid exact candidate archive');
  return bytes;
}

export function composeSuccessorIntent({selection,prior,observed,evidence,sourceProof,
  rebuiltArchive,mirrorArchive}) {
  // Selection is an independently reviewed immutable digest/run identity, NOT
  // an owner publication request or a value inferred from candidate logs.
  fields(selection,['version','previousVersion','previousReceiptSha256','sourceCommit',
    'manifestSha256','candidateSha256','platformSource','qualificationEvent',
    'nativeSourceMain','platformMain'],'selected successor');
  for(const k of ['sourceCommit','platformSource']) need(exact(selection[k],sha),'Exact selected commit required');
  for(const k of ['previousReceiptSha256','manifestSha256','candidateSha256'])
    need(exact(selection[k],digest),'Exact selected digest required');
  fields(prior,['receiptBytes','archiveBytes','registry','platformSource','componentDigests'],
    'predecessor inputs');
  fields(observed,['manifestBytes','sourceCommit','previousSourceCommit','historicalSourceCommit',
    'shellTree','componentDigests','coreVersion','platformSource','qualificationEvent',
    'nativeSourceMain','platformMain'],'independent successor observations');
  const previous=verifyPriorRegistryArchive({...prior,expectedVersion:selection.previousVersion,
    expectedSha256:selection.previousReceiptSha256}).previous;
  const receipt=validateNativeReceipt(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(prior.receiptBytes)),
    selection.previousVersion);
  need(receipt.source.commit===observed.previousSourceCommit,'Previous source commit differs from exact native receipt');
  for(const k of ['sourceCommit','platformSource','qualificationEvent','nativeSourceMain','platformMain'])
    need(equal(observed[k],selection[k]),'Independent source/CI differs from reviewed selection');

  const rebuilt=archive(rebuiltArchive), mirror=archive(mirrorArchive);
  need(rebuilt.equals(mirror)&&hash(rebuilt)===selection.candidateSha256,
    'Independently rebuilt archive differs from selection or public mirror');
  const projection=readReleaseArchiveProjection({archiveBytes:rebuilt,
    expectedVersion:selection.version,requirePublishableForm:true});
  const comparison=compareSuccessorEvidence({
    manifestBytes:observed.manifestBytes,prior:previous,evidence,projection,
    observed:{targetVersion:selection.version,sourceCommit:observed.sourceCommit,
      previousSourceCommit:observed.previousSourceCommit,
      historicalSourceCommit:observed.historicalSourceCommit,shellTree:observed.shellTree,
      manifestSha256:selection.manifestSha256,componentDigests:observed.componentDigests,
      coreVersion:observed.coreVersion}
  });
  // Compare the exact success proof from the selected private run, not a
  // candidate's self-declared authority. The protected caller binds its origin.
  need(equal(sourceProof,{
    schemaVersion:1,kind:'project-forge-offline-native-successor-proof',
    sourceCommit:selection.sourceCommit,previousVersion:selection.previousVersion,
    previousReceiptSha256:selection.previousReceiptSha256,version:selection.version,
    manifestSha256:selection.manifestSha256,candidateSha256:selection.candidateSha256,
    changedComponents:comparison.changedComponents,components:evidence.components,
    reproducibleArchive:true,disposableAllComponents:true,disposableGeneratedConsumers:true,
    previousAcceptanceAuthenticatedHere:false,releaseAuthorized:false,published:false,
    productionAuthorized:false,sourceOwnershipTransferred:false
  }),'Exact source qualification proof differs');
  const intent=constructNativeIntent({
    package:{name:'@mriekki/project-forge',version:selection.version},
    platformSource:selection.platformSource,source:{mode:'native-monorepo',
      commit:selection.sourceCommit,previousVersion:selection.previousVersion,
      previousReceiptSha256:selection.previousReceiptSha256,manifestSha256:selection.manifestSha256,
      qualificationEvent:selection.qualificationEvent},
    components:comparison.components,ci:{nativeSourceMain:selection.nativeSourceMain,
      platformMain:selection.platformMain},candidateSha256:selection.candidateSha256
  });
  const verified=verifyNativeStableCandidate({intent,prior,candidateArchiveBytes:rebuilt,
    observedSource:{platformSource:observed.platformSource,sourceCommit:observed.sourceCommit,
      manifestSha256:selection.manifestSha256,qualificationEvent:observed.qualificationEvent,
      nativeSourceMain:observed.nativeSourceMain,platformMain:observed.platformMain,
      componentDigests:observed.componentDigests}});
  return {intent,changedComponents:comparison.changedComponents,
    result:'NATIVE_SUCCESSOR_INTENT_EVIDENCE_MATCH',sourceProofMatched:true,
    archiveMirrorMatched:true,priorArchiveReceiptMatched:verified.priorArchiveReceiptMatched,
    sourceEvidenceAuthenticatedHere:false,registrySignatureVerifiedHere:false,
    releaseAuthorized:false,publicationAuthorized:false,productionAuthorized:false,
    sourceOwnershipTransferred:false};
}
