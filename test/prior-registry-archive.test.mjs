import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { verifyPriorRegistryArchive } from '../scripts/prior-registry-archive.mjs';
import { verifyReleasedContractAlignment } from '../scripts/native-release-contract-alignment.mjs';
import { verifyNativeStableCandidate } from '../scripts/native-stable-candidate-verifier.mjs';
import { constructNativeIntent } from '../scripts/native-source-receipt.mjs';

const hash = (algorithm, bytes, encoding = 'hex') =>
  createHash(algorithm).update(bytes).digest(encoding);
const oldBytes = fs.readFileSync(new URL('../release/receipts/4.35.0.json', import.meta.url));
const old = JSON.parse(oldBytes);
const stableDescriptor = JSON.parse(fs.readFileSync(new URL('../chatgpt/current.json', import.meta.url)));
function fixture(change = () => {}, native = false) {
  const receipt = structuredClone(old);
  const componentDigests = Object.fromEntries(Object.keys(receipt.components).map((id,i)=>[id,String(i+1).repeat(64)]));
  if (native) {
    const head = 'a'.repeat(40);
    componentDigests.feedback = '7'.repeat(64);
    receipt.schemaVersion = 2;
    receipt.kind = 'project-forge-native-source-release';
    receipt.package.version = '4.36.0';
    receipt.platformSource = 'b'.repeat(40);
    receipt.source = {mode:'native-monorepo',commit:head,previousVersion:'4.35.0',
      manifestSha256:'c'.repeat(64),previousReceiptSha256:hash('sha256',oldBytes),
      qualificationEvent:'issues'};
    for (const id of Object.keys(receipt.components)) {
      Object.assign(receipt.components[id], {revisionKind:'original-owner-git-commit',
        mappedInputSha256:componentDigests[id]});
    }
    Object.assign(receipt.components.feedback, {revision:head,
      revisionKind:'private-monorepo-git-commit'});
    // All publication/run values in this fixture are synthetic, not live evidence.
    receipt.publication = {publishedAt:'2026-01-01T00:00:00Z',workflowRunId:10,
      publisher:'github-oidc',registryIdentity:'verified',neutralNpxSmoke:'verified',
      provenance:{signed:true,transparencyLogUrl:'https://search.sigstore.dev/?logIndex=20'}};
    receipt.ci = {nativeSourceMain:{result:'success',workflowRunId:30,runAttempt:1},
      platformMain:{result:'success',workflowRunId:31,runAttempt:1}};
  }
  const descriptor = structuredClone(stableDescriptor);
  descriptor.generation.packageVersion = receipt.package.version;
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'pf-prior-archive-'));
  try {
    const metadata = {schemaVersion:2, package:receipt.package.name,
      version:receipt.package.version,
      profiles:{'greenfield-project':{components:['core','deployment']}},
      components:Object.fromEntries(Object.entries(receipt.components).map(([id, item]) => [
        id, id === 'core' ? {revision:item.revision,version:item.version} : {revision:item.revision}
      ]))};
    const docs = {
      'package.json':{...receipt.package,publishConfig:{access:'public',provenance:true}},
      'assets/components.json':metadata,
      'assets/generated/ASSEMBLY.json':structuredClone(metadata)
    };
    change(docs);
    for (const [name,doc] of Object.entries(docs)) {
      const file = path.join(root,'package',name);
      fs.mkdirSync(path.dirname(file),{recursive:true});
      fs.writeFileSync(file,JSON.stringify(doc));
    }
    const archiveBytes = execFileSync('tar',['-czf','-','-C',root,'package']);
    receipt.artifact = {releaseCandidateSha256:hash('sha256',archiveBytes),
      registryShasum:hash('sha1',archiveBytes)};
    const receiptBytes = Buffer.from(JSON.stringify(receipt));
    return {descriptor,receiptBytes,expectedVersion:receipt.package.version,expectedSha256:hash('sha256',receiptBytes),
      archiveBytes,registry:{...receipt.package,dist:{shasum:receipt.artifact.registryShasum,
        integrity:'sha512-'+hash('sha512',archiveBytes,'base64')}},
      platformSource:receipt.platformSource,
      componentDigests};
  } finally {
    fs.rmSync(root,{recursive:true,force:true});
  }
}
test('matching synthetic registry archive and exact receipt yield prior projection only',()=>{
  const result = verifyPriorRegistryArchive(fixture());
  assert.equal(result.previous.version,'4.35.0');
  assert.equal(result.previous.components.core.revisionKind,'original-owner-git-commit');
  for (const key of ['archiveReceiptMatched','registryIntegrityMatched']) assert.equal(result[key],true);
  for (const key of ['priorReceiptAuthenticatedHere','sourceEvidenceAuthenticatedHere',
    'signatureVerifiedHere','releaseAuthorized','sourceOwnershipTransferred','productionAuthorized'])
    assert.equal(result[key],false);
});
test('reject changed receipts, archive, registry, source evidence or missing mapped digest',()=>{
  for (const mutate of [
    x=>x.expectedSha256='0'.repeat(64),
    x=>x.archiveBytes=Buffer.concat([x.archiveBytes,Buffer.from('changed')]),
    x=>x.registry.name='wrong', x=>x.registry.version='4.36.0',
    x=>x.registry.dist.shasum='0'.repeat(40), x=>x.registry.dist.integrity='sha512-wrong',
    x=>x.platformSource='0'.repeat(40), x=>delete x.componentDigests.core
  ]) {
    const x=fixture();mutate(x);assert.throws(()=>verifyPriorRegistryArchive(x));
  }
});
test('reject incompatible package and component observations even when archive hashes agree',()=>{
  for (const mutate of [
    x=>x['package.json'].private=true,
    x=>x['package.json'].version='4.36.0',
    x=>x['assets/components.json'].components.core.version='99.0.0',
    x=>x['assets/generated/ASSEMBLY.json'].components.feedback.revision='0'.repeat(40),
    x=>delete x['assets/components.json'].components.feedback,
    x=>{
      x['assets/components.json'].components.feedback.revision='0'.repeat(40);
      x['assets/generated/ASSEMBLY.json'].components.feedback.revision='0'.repeat(40);
    }
  ]) assert.throws(()=>verifyPriorRegistryArchive(fixture(mutate)));
});

test('stable descriptor alignment compares exact legacy and native archive profile evidence only',()=>{
  for (const native of [false,true]) {
    const input=fixture(()=>{},native);
    const result=verifyReleasedContractAlignment(input);
    assert.equal(result.packageVersion,input.expectedVersion);
    assert.equal(result.selectedProfile,'greenfield-project');
    assert.equal(result.result,'RELEASE_CONTRACT_EVIDENCE_MATCH');
    assert.equal(result.receiptSha256,input.expectedSha256);
    for (const key of ['archiveReceiptMatched','registryIntegrityMatched','descriptorSelectionMatched'])
      assert.equal(result[key],true);
    for (const key of ['descriptorDocumentsVerifiedHere','receiptAuthenticatedHere',
      'sourceEvidenceAuthenticatedHere','signatureVerifiedHere','alignmentAuthorized',
      'releaseAuthorized','sourceOwnershipTransferred','productionAuthorized'])
      assert.equal(result[key],false);
  }
});

test('native alignment refuses stale descriptor or unrecognized archive profile',()=>{
  for (const mutate of [
    x=>x.descriptor.channel='preview',
    x=>x.descriptor.generation.packageVersion='4.35.0',
    x=>x.descriptor.generation.profile='unknown-project',
    x=>x.descriptor.generation.bootstrap.revision='main',
    x=>x.descriptor.snapshotPath='chatgpt/contracts/v999',
    x=>x.expectedSha256='0'.repeat(64),
    x=>x.componentDigests.feedback='9'.repeat(64)
  ]) {
    const input=fixture(()=>{},true);mutate(input);
    assert.throws(()=>verifyReleasedContractAlignment(input));
  }
  for (const change of [
    x=>delete x['assets/components.json'].profiles,
    x=>x['assets/components.json'].profiles['greenfield-project'].components=['core'],
    x=>x['assets/components.json'].profiles['greenfield-project'].components=['core','deployment','core'],
    x=>x['assets/components.json'].profiles['greenfield-project'].components=['core','deployment','unknown']
  ]) assert.throws(()=>verifyReleasedContractAlignment(fixture(change,true)),/generation profile/);
});

test('native receipt shape must remain distinct from legacy and prepublication intent',()=>{
  for (const mutate of [
    x=>x.schemaVersion=99,
    x=>x.kind='project-forge-native-release-intent',
    x=>x.source.sourceRepositoryUrl='https://example.invalid',
    x=>x.components.feedback.revisionKind='invented',
    x=>x.publication.provenance.signed=false,
    x=>x.ci.nativeSourceMain.runAttempt=0
  ]) {
    const input=fixture(()=>{},true);
    const receipt=JSON.parse(input.receiptBytes);
    mutate(receipt);
    input.receiptBytes=Buffer.from(JSON.stringify(receipt));
    input.expectedSha256=hash('sha256',input.receiptBytes);
    assert.throws(()=>verifyReleasedContractAlignment(input));
  }
});

function candidateFixture(change = () => {}) {
  const previous = fixture();
  const candidate = fixture(change,true);
  const nextReceipt = JSON.parse(candidate.receiptBytes);
  nextReceipt.source.previousReceiptSha256 = previous.expectedSha256;
  const {package: packageInfo, platformSource, source, components, ci} = nextReceipt;
  const intent = constructNativeIntent({
    package:packageInfo, platformSource, source, components, ci,
    candidateSha256:hash('sha256',candidate.archiveBytes)
  });
  const prior = {
    receiptBytes:previous.receiptBytes, archiveBytes:previous.archiveBytes,
    registry:previous.registry, platformSource:previous.platformSource,
    componentDigests:previous.componentDigests
  };
  return { intent, prior, candidateArchiveBytes:candidate.archiveBytes,
    observedSource:{
      platformSource,sourceCommit:source.commit,manifestSha256:source.manifestSha256,
      qualificationEvent:source.qualificationEvent,nativeSourceMain:ci.nativeSourceMain,
      platformMain:ci.platformMain,componentDigests:candidate.componentDigests
    }
  };
}

test('exact synthetic native stable candidate matches intent and prior registry archive without authority',()=>{
  const input=candidateFixture();
  const proof=verifyNativeStableCandidate(input);
  assert.equal(proof.result,'NATIVE_STABLE_CANDIDATE_EVIDENCE_MATCH');
  assert.equal(proof.changedComponents,1);
  assert.equal(proof.candidateSha256,input.intent.candidateSha256);
  for (const key of ['priorArchiveReceiptMatched','candidateArchiveMatched'])
    assert.equal(proof[key],true);
  for (const key of ['sourceEvidenceAuthenticatedHere','priorReceiptAuthenticatedHere',
    'registrySignatureVerifiedHere','releaseAuthorized','publicationAuthorized',
    'sourceOwnershipTransferred','productionAuthorized'])
    assert.equal(proof[key],false);
});

test('candidate verification refuses mismatched archive, prior receipt and independent evidence',()=>{
  for (const mutate of [
    x=>x.intent.candidateSha256='0'.repeat(64),
    x=>x.prior.registry.dist.integrity='sha512-wrong',
    x=>x.intent.source.previousReceiptSha256='0'.repeat(64),
    x=>x.observedSource.nativeSourceMain={result:'success',workflowRunId:30,runAttempt:2},
    x=>x.observedSource.sourceCommit='0'.repeat(40),
    x=>x.observedSource.componentDigests.feedback='9'.repeat(64),
    x=>x.observedSource.releaseAuthorized=true,
    x=>x.intent.releaseAuthorized=true,
    x=>x.intent.components.feedback.revisionKind='original-owner-git-commit'
  ]) {
    const input=candidateFixture();
    mutate(input);
    assert.throws(()=>verifyNativeStableCandidate(input));
  }
});

test('stable candidate verifier refuses rehearsal/private and inconsistent archive even with matching intent digest',()=>{
  for (const change of [
    x=>x['package.json'].private=true,
    x=>x['package.json'].private='false',
    x=>delete x['package.json'].publishConfig,
    x=>x['package.json'].publishConfig.provenance=false,
    x=>x['package.json'].version='4.36.0-preview.7',
    x=>x['assets/components.json'].components.feedback.revision='0'.repeat(40),
    x=>x['assets/generated/ASSEMBLY.json'].components.core.version='0.0.0',
    x=>{
      x['assets/components.json'].components.feedback.revision='0'.repeat(40);
      x['assets/generated/ASSEMBLY.json'].components.feedback.revision='0'.repeat(40);
    },
  ]) assert.throws(()=>verifyNativeStableCandidate(candidateFixture(change)));
});

import {composeSuccessorIntent} from '../scripts/native-successor-intent.mjs';
import {classifyNativeIntentRecovery} from '../scripts/native-source-receipt.mjs';

function successorFixture(changed=true) {
  const predecessor=fixture(()=>{},true);
  const receipt=JSON.parse(predecessor.receiptBytes);
  const version='4.36.1', sourceCommit='d'.repeat(40);
  const ids=Object.keys(receipt.components).sort();
  const old=Object.fromEntries(ids.map(id=>{
    const {version:ignored,...rest}=receipt.components[id];return [id,rest];
  }));
  const next=structuredClone(old);
  if(changed) next.feedback={revision:sourceCommit,revisionKind:'private-monorepo-git-commit',
    mappedInputSha256:'8'.repeat(64)};
  const componentDigests=Object.fromEntries(ids.map(id=>[id,next[id].mappedInputSha256]));
  const historicalSourceCommit='e'.repeat(40),shellTree='f'.repeat(40);
  const manifestBytes=Buffer.from(JSON.stringify({
    schemaVersion:2,kind:'project-forge-native-stable-candidate-assembly',package:receipt.package.name,
    version,previousVersion:receipt.package.version,previousReceiptSha256:predecessor.expectedSha256,
    sourceCommit,previousSourceCommit:receipt.source.commit,historicalSourceCommit,shellTree,
    previousComponents:old,allowPublish:false,allowProduction:false
  }));
  const candidate=fixture(docs=>{
    docs['package.json'].version=version;
    for(const file of ['assets/components.json','assets/generated/ASSEMBLY.json']){
      docs[file].version=version;
      for(const id of ids) docs[file].components[id].revision=next[id].revision;
    }
  },true);
  const selection={version,previousVersion:receipt.package.version,previousReceiptSha256:predecessor.expectedSha256,
    sourceCommit,manifestSha256:hash('sha256',manifestBytes),
    candidateSha256:hash('sha256',candidate.archiveBytes),platformSource:'c'.repeat(40),
    qualificationEvent:'issues',nativeSourceMain:{result:'success',workflowRunId:40,runAttempt:1},
    platformMain:{result:'success',workflowRunId:41,runAttempt:1}};
  const changedComponents=changed?['feedback']:[];
  const evidence={schemaVersion:2,kind:'project-forge-native-stable-candidate-evidence',
    sourceCommit,manifestSha256:selection.manifestSha256,packageVersion:version,components:next,
    changedComponents,previousVersion:selection.previousVersion,previousReceiptSha256:selection.previousReceiptSha256,
    archiveForm:'public-stable',releaseAuthorized:false,previousAcceptanceAuthenticatedHere:false,
    sourceOwnershipTransferred:false,published:false,productionAuthorized:false};
  const sourceProof={schemaVersion:1,kind:'project-forge-offline-native-successor-proof',
    sourceCommit,previousVersion:selection.previousVersion,previousReceiptSha256:selection.previousReceiptSha256,
    version,manifestSha256:selection.manifestSha256,candidateSha256:selection.candidateSha256,
    changedComponents:[...changedComponents],components:structuredClone(next),reproducibleArchive:true,
    disposableAllComponents:true,disposableGeneratedConsumers:true,previousAcceptanceAuthenticatedHere:false,
    releaseAuthorized:false,published:false,productionAuthorized:false,sourceOwnershipTransferred:false};
  const observed={manifestBytes,sourceCommit,previousSourceCommit:receipt.source.commit,historicalSourceCommit,
    shellTree,componentDigests,coreVersion:receipt.components.core.version,platformSource:selection.platformSource,
    qualificationEvent:selection.qualificationEvent,nativeSourceMain:structuredClone(selection.nativeSourceMain),
    platformMain:structuredClone(selection.platformMain)};
  const prior={receiptBytes:predecessor.receiptBytes,archiveBytes:predecessor.archiveBytes,
    registry:predecessor.registry,platformSource:predecessor.platformSource,
    componentDigests:predecessor.componentDigests};
  return {selection,prior,observed,evidence,sourceProof,rebuiltArchive:candidate.archiveBytes,
    mirrorArchive:Buffer.from(candidate.archiveBytes)};
}

test('compose repeatable v2 successor intent from registry predecessor, dual archives and exact source proof',()=>{
  for(const changed of [true,false]){
    const input=successorFixture(changed);
    const result=composeSuccessorIntent(input);
    assert.equal(result.result,'NATIVE_SUCCESSOR_INTENT_EVIDENCE_MATCH');
    assert.deepEqual(result.changedComponents,changed?['feedback']:[]);
    const old=JSON.parse(input.prior.receiptBytes);
    assert.equal(result.intent.components.feedback.revision,
      changed?input.selection.sourceCommit:old.components.feedback.revision);
    assert.deepEqual(result.intent.components.core,old.components.core);
    assert.equal(result.intent.candidateSha256,input.selection.candidateSha256);
    for(const key of ['releaseAuthorized','publicationAuthorized','productionAuthorized','sourceOwnershipTransferred',
      'sourceEvidenceAuthenticatedHere','registrySignatureVerifiedHere']) assert.equal(result[key],false);
    const recover=classifyNativeIntentRecovery({intent:result.intent,existingReceipt:null,registry:{
      status:'present',package:result.intent.package,artifact:{releaseCandidateSha256:result.intent.candidateSha256,
      registryShasum:hash('sha1',input.rebuiltArchive)}}});
    assert.equal(recover.decision,'VERIFY_EXISTING_PUBLICATION_NO_REPUBLISH');
    assert.equal(recover.publishAuthorized,false);
  }
});

test('successor intent refuses stale, altered, incomplete and independently mismatched evidence',()=>{
  for(const mutate of [
    x=>x.selection.previousReceiptSha256='0'.repeat(64),
    x=>x.prior.registry.dist.integrity='wrong',
    x=>x.observed.previousSourceCommit='0'.repeat(40),
    x=>x.observed.nativeSourceMain.runAttempt++,
    x=>x.observed.platformMain.workflowRunId++,
    x=>x.sourceProof.disposableAllComponents=false,
    x=>x.sourceProof.reproducibleArchive=false,
    x=>x.sourceProof.sourceCommit='0'.repeat(40),
    x=>x.sourceProof.changedComponents=[],
    x=>x.sourceProof.components.feedback.revision='0'.repeat(40),
    x=>x.sourceProof.releaseAuthorized=true,
    x=>x.evidence.components.authentication.revision='0'.repeat(40),
    x=>x.mirrorArchive[0]^=1,
    x=>x.rebuiltArchive[0]^=1,
    x=>x.selection.candidateSha256='0'.repeat(64),
    x=>x.observed.manifestBytes[0]^=1,
    x=>x.selection.releaseAuthorized=true
  ]) {const input=successorFixture();mutate(input);assert.throws(()=>composeSuccessorIntent(input));}
});
