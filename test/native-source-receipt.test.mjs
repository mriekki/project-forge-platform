import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateReleaseReceipt, loadReleaseReceipt, resolvePublishedPlatformSource } from '../scripts/release-receipt.mjs';
import os from 'node:os';
import {validateNativeReceipt,constructNativeReceipt,verifyNativeProjection,
  classifyNativeRecovery,constructNativeIntent,validateNativeIntent,verifyNativeIntent,
  constructNativeReceiptFromIntent,verifyReceiptMatchesIntent,classifyNativeIntentRecovery} from '../scripts/native-source-receipt.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const old = JSON.parse(fs.readFileSync(path.join(root,'release/receipts/4.35.0.json'),'utf8'));
const head = 'a'.repeat(40), nextHead = 'b'.repeat(40);
const COMPONENTS = ['authentication','core','deployment','feedback','release-notes'];
function fixture() {
  const previous = {version: old.package.version, receiptSha256:'0'.repeat(64), components: Object.fromEntries(COMPONENTS.map((id,i) =>
    [id, {...old.components[id], revisionKind:'original-owner-git-commit',
      mappedInputSha256: String(i+1).repeat(64)}]))};
  const facts = {
    package:{name:'@mriekki/project-forge',version:'4.36.0'},
    platformSource:'c'.repeat(40),
    source:{mode:'native-monorepo',commit:head,previousVersion:previous.version,
      manifestSha256:'d'.repeat(64),previousReceiptSha256:previous.receiptSha256,qualificationEvent:'issues'},
    components:structuredClone(previous.components),
    artifact:{releaseCandidateSha256:'e'.repeat(64),registryShasum:'f'.repeat(40)},
    publication:{publishedAt:'2026-01-01T00:00:00Z',workflowRunId:10,publisher:'github-oidc',
      registryIdentity:'verified',neutralNpxSmoke:'verified',
      provenance:{signed:true,transparencyLogUrl:'https://search.sigstore.dev/?logIndex=20'}},
    ci:{nativeSourceMain:{result:'success',workflowRunId:30,runAttempt:1},
      platformMain:{result:'success',workflowRunId:31,runAttempt:1}}
  };
  facts.components.feedback = {revision:head,revisionKind:'private-monorepo-git-commit',
    mappedInputSha256:'9'.repeat(64)};
  const receipt = constructNativeReceipt(facts);
  const observed = {
    packageVersion:receipt.package.version,platformSource:receipt.platformSource,
    sourceCommit:receipt.source.commit,manifestSha256:receipt.source.manifestSha256,
    qualificationEvent:receipt.source.qualificationEvent,
    nativeSourceMain:structuredClone(receipt.ci.nativeSourceMain),
    platformMain:structuredClone(receipt.ci.platformMain),
    componentDigests:Object.fromEntries(COMPONENTS.map(id=>[id,receipt.components[id].mappedInputSha256])),
    packageComponents:Object.fromEntries(COMPONENTS.map(id=>[id,id==='core'
      ? {revision:receipt.components[id].revision,version:receipt.components[id].version}
      : {revision:receipt.components[id].revision}])),
    assemblyRevisions:Object.fromEntries(COMPONENTS.map(id=>[id,receipt.components[id].revision])),
    artifact:structuredClone(receipt.artifact),publication:structuredClone(receipt.publication)
  };
  return {receipt,previous,observed};
}
test('native source fixture preserves the legacy reader and untouched historical receipt',()=>{
  assert.equal(validateReleaseReceipt(old).schemaVersion,1);
  const x=fixture();
  assert.equal(validateNativeReceipt(x.receipt,'4.36.0').schemaVersion,2);
  assert.throws(()=>validateReleaseReceipt(x.receipt),/schemaVersion/);
  assert.throws(()=>validateNativeReceipt(old),/native receipt/);
  const result=verifyNativeProjection(x);
  assert.equal(result.changedComponents,1);
  assert.equal(result.sourceEvidenceAuthenticatedHere,false);
  assert.equal(result.releaseAuthorized,false);
});
test('unrelated source advance preserves prior native component identity',()=>{
  const a=fixture();
  const b=fixture();
  b.previous={version:a.receipt.package.version,receiptSha256:'1'.repeat(64),components:structuredClone(a.receipt.components)};
  b.receipt.package.version='4.37.0';
  b.receipt.source.previousVersion=a.receipt.package.version;
  b.receipt.source.previousReceiptSha256=b.previous.receiptSha256;
  b.receipt.source.commit=nextHead;
  b.observed.packageVersion=b.receipt.package.version;
  b.observed.sourceCommit=nextHead;
  assert.equal(verifyNativeProjection(b).changedComponents,0);
  b.receipt.components.feedback.revision=nextHead;
  b.observed.packageComponents.feedback.revision=nextHead;
  b.observed.assemblyRevisions.feedback=nextHead;
  assert.throws(()=>verifyNativeProjection(b),/identity continuity/);
});
test('reject schema, kind, privacy, authority, version and incomplete publication evidence',()=>{
  const mutations = [
    x=>x.schemaVersion=3, x=>x.kind='unknown',
    x=>x.source.repository='private/fixture',
    x=>x.source.sourceRepositoryUrl='https://example.invalid',
    x=>x.components.feedback.revisionKind='sha256-digest',
    x=>x.artifact.registryShasum='bad',
    x=>x.releaseAuthorized=true, x=>x.source.commit='main',
    x=>x.package.version=x.source.previousVersion, x=>x.package.version='4.36.0-preview.2',
    x=>x.publication.provenance.signed=false,
    x=>x.publication.provenance.transparencyLogUrl='https://example.invalid',
    x=>x.publication.publishedAt='2026-02-31T00:00:00Z',
    x=>x.ci.nativeSourceMain.result='skipped', x=>x.ci.nativeSourceMain.runAttempt=0,
    x=>x.ci.feedbackMain={result:'success',workflowRunId:30},
    x=>x.components.feedback.sourceRepository='private/fixture'
  ];
  for(const mutate of mutations) {
    const x=fixture().receipt; mutate(x); assert.throws(()=>validateNativeReceipt(x));
  }
});
test('reject stale selected source, wrong attempt, digests, archive or compatibility projection',()=>{
  const mutations=[
    x=>x.observed.sourceCommit=nextHead,
    x=>x.observed.nativeSourceMain.runAttempt=2,
    x=>x.observed.componentDigests.feedback='8'.repeat(64),
    x=>x.observed.packageComponents.feedback.revision=nextHead,
    x=>x.observed.assemblyRevisions.feedback=nextHead,
    x=>x.observed.artifact.releaseCandidateSha256='8'.repeat(64),
    x=>x.observed.publication.workflowRunId=100,
    x=>x.receipt.components.feedback.revisionKind='original-owner-git-commit',
    x=>x.receipt.components.feedback.revision=x.previous.components.feedback.revision,
    x=>x.previous.version='4.34.0'
  ];
  for(const mutate of mutations) {
    const x=fixture(); mutate(x); assert.throws(()=>verifyNativeProjection(x));
  }
});
test('interrupted publication never implies republish, receipt write or alignment authorization',()=>{
  const expectedReceipt=fixture().receipt;
  const context={expectedReceipt,existingReceipt:null,
    registry:{status:'present',package:structuredClone(expectedReceipt.package),
      artifact:structuredClone(expectedReceipt.artifact)}};
  const result=classifyNativeRecovery(context);
  assert.equal(result.decision,'VERIFY_EXISTING_PUBLICATION_NO_REPUBLISH');
  for(const key of ['publishAuthorized','receiptWriteAuthorized','alignmentAuthorized'])
    assert.equal(result[key],false);
  assert.equal(classifyNativeRecovery({...context,existingReceipt:expectedReceipt}).decision,
    'MATCHED_RECEIPT_VERIFY_ALIGNMENT');
  assert.equal(classifyNativeRecovery({...context,registry:{status:'unknown'}}).decision,
    'BLOCKED_REGISTRY_UNVERIFIED');
  assert.equal(classifyNativeRecovery({...context,registry:{status:'absent'}}).decision,
    'NOT_PUBLISHED_NEW_AUTHORIZATION_REQUIRED');
  assert.equal(classifyNativeRecovery({...context,registry:{status:'absent'},existingReceipt:expectedReceipt}).decision,
    'BLOCKED_RECEIPT_WITHOUT_REGISTRY');
  const mismatch=structuredClone(context);
  mismatch.registry.artifact.registryShasum='0'.repeat(40);
  assert.equal(classifyNativeRecovery(mismatch).decision,'BLOCKED_REGISTRY_CONFLICT');
  const wrongReceipt=structuredClone(expectedReceipt);
  wrongReceipt.publication.workflowRunId++;
  assert.equal(classifyNativeRecovery({...context,existingReceipt:wrongReceipt}).decision,
    'BLOCKED_RECEIPT_CONFLICT');
});

function intentFixture() {
  const {receipt,previous,observed} = fixture();
  const {package:packageInfo,platformSource,source,components,ci} = receipt;
  const intent=constructNativeIntent({package:packageInfo,platformSource,source,components,ci,
    candidateSha256:receipt.artifact.releaseCandidateSha256});
  const {artifact,publication,...observation} = observed;
  observation.candidateSha256=artifact.releaseCandidateSha256;
  return {intent,previous,observed:observation,receipt};
}
test('prepublication intent does not contain fictitious signed receipt facts',()=>{
  const {intent,previous,observed,receipt}=intentFixture();
  assert.equal(verifyNativeIntent({intent,previous,observed}).result,'NATIVE_INTENT_MATCH');
  assert.equal(Object.hasOwn(intent,'publication'),false);
  assert.equal(Object.hasOwn(intent,'artifact'),false);
  assert.equal(intent.releaseAuthorized,false);
  assert.throws(()=>validateNativeReceipt(intent),/native receipt/);
  assert.throws(()=>constructNativeReceiptFromIntent(intent,{}),/postpublication facts/);
  assert.deepEqual(constructNativeReceiptFromIntent(intent,{
    artifact:receipt.artifact,publication:receipt.publication
  }),receipt);
  const wrong=structuredClone(receipt);
  wrong.source.previousReceiptSha256='3'.repeat(64);
  assert.throws(()=>verifyReceiptMatchesIntent(wrong,intent),/selected intent/);
});
test('prepublication intent binds prior receipt bytes and new artifact, refuses misleading fields',()=>{
  const mutations=[
    x=>x.previous.receiptSha256='1'.repeat(64),
    x=>x.observed.candidateSha256='1'.repeat(64),
    x=>x.observed.sourceCommit=nextHead,
    x=>x.intent.source.previousReceiptSha256='bad',
    x=>x.intent.releaseAuthorized=true,
    x=>x.intent.publication={provenance:{signed:true}},
    x=>x.intent.package.version=x.intent.source.previousVersion
  ];
  for(const mutate of mutations) {
    const x=intentFixture();mutate(x);assert.throws(()=>verifyNativeIntent(x));
  }
});
test('intent recovery before and after actual publication never implies write authority',()=>{
  const {intent,receipt}=intentFixture();
  const input={intent,existingReceipt:null,registry:{status:'unknown'}};
  assert.equal(classifyNativeIntentRecovery(input).decision,'BLOCKED_REGISTRY_UNVERIFIED');
  assert.equal(classifyNativeIntentRecovery({...input,registry:{status:'absent'}}).decision,
    'NOT_PUBLISHED_NEW_AUTHORIZATION_REQUIRED');
  const present={status:'present',package:receipt.package,artifact:receipt.artifact};
  assert.equal(classifyNativeIntentRecovery({...input,registry:present}).decision,
    'VERIFY_EXISTING_PUBLICATION_NO_REPUBLISH');
  const matched=classifyNativeIntentRecovery({...input,registry:present,existingReceipt:receipt});
  assert.equal(matched.decision,'MATCHED_RECEIPT_VERIFY_ALIGNMENT');
  for (const k of ['publishAuthorized','receiptWriteAuthorized','alignmentAuthorized'])
    assert.equal(matched[k],false);
  const changed=structuredClone(present);
  changed.artifact.registryShasum='1'.repeat(40);
  assert.equal(classifyNativeIntentRecovery({...input,registry:changed,existingReceipt:receipt}).decision,
    'BLOCKED_RECEIPT_CONFLICT');
  changed.artifact.releaseCandidateSha256='1'.repeat(64);
  assert.equal(classifyNativeIntentRecovery({...input,registry:changed}).decision,
    'BLOCKED_REGISTRY_CONFLICT');
});


// Exact byte selection and independent prior observations are a separate
// adapter; no new live receipt reader or publishing authority.
import { createHash } from 'node:crypto';
import { selectPriorRelease, verifyIntentWithPriorReceipt } from '../scripts/prior-release-projection.mjs';
const actualOldBytes = fs.readFileSync(path.join(root,'release/receipts/4.35.0.json'));
const digestBytes = bytes => createHash('sha256').update(bytes).digest('hex');
function priorFacts(record, componentDigests) {
  return {
    package:structuredClone(record.package),platformSource:record.platformSource,
    artifact:structuredClone(record.artifact),
    packageComponents:Object.fromEntries(COMPONENTS.map(cid=>[cid,cid==='core'
      ? {revision:record.components[cid].revision,version:record.components[cid].version}
      : {revision:record.components[cid].revision}])),
    componentDigests
  };
}
test('exact historical receipt bytes connect to dormant native intent without inventing digests',()=>{
  const {intent,previous,observed}=intentFixture();
  intent.source.previousReceiptSha256=digestBytes(actualOldBytes);
  const priorObserved=priorFacts(old,Object.fromEntries(COMPONENTS.map(cid=>[
    cid,previous.components[cid].mappedInputSha256])));
  const projection=selectPriorRelease({receiptBytes:actualOldBytes,expectedVersion:'4.35.0',
    expectedSha256:intent.source.previousReceiptSha256,observed:priorObserved});
  assert.deepEqual(projection.components,previous.components);
  const result=verifyIntentWithPriorReceipt({intent,receiptBytes:actualOldBytes,
    priorObserved,candidateObserved:observed});
  assert.equal(result.result,'NATIVE_INTENT_MATCH');
  assert.equal(result.priorReceiptBytesMatched,true);
  assert.equal(result.priorReceiptAuthenticatedHere,false);
  assert.equal(result.releaseAuthorized,false);
  const changed=Buffer.concat([actualOldBytes,Buffer.from('\n')]);
  assert.throws(()=>verifyIntentWithPriorReceipt({intent,receiptBytes:changed,
    priorObserved,candidateObserved:observed}),/receipt digest mismatch/);
  priorObserved.artifact.registryShasum='0'.repeat(40);
  assert.throws(()=>verifyIntentWithPriorReceipt({intent,receiptBytes:actualOldBytes,
    priorObserved,candidateObserved:observed}),/source\/archive proof differs/);
});
test('versioned prior receipt preserves native identity and refuses mismatched independent evidence',()=>{
  const record=fixture().receipt;
  const bytes=Buffer.from(JSON.stringify(record));
  const observed=priorFacts(record,Object.fromEntries(COMPONENTS.map(cid=>[
    cid,record.components[cid].mappedInputSha256])));
  const input={receiptBytes:bytes,expectedVersion:record.package.version,
    expectedSha256:digestBytes(bytes),observed};
  assert.deepEqual(selectPriorRelease(input).components,record.components);
  for (const mutate of [
    x=>x.observed.componentDigests.feedback='1'.repeat(64),
    x=>x.observed.packageComponents.feedback.revision=nextHead,
    x=>x.observed.platformSource=nextHead,
    x=>x.expectedVersion='4.37.0',
    x=>delete x.observed.componentDigests.core
  ]) {
    const x={...input,observed:structuredClone(observed)};mutate(x);
    assert.throws(()=>selectPriorRelease(x));
  }
  const unknown=Buffer.from(JSON.stringify({...record,schemaVersion:7}));
  assert.throws(()=>selectPriorRelease({...input,receiptBytes:unknown,expectedSha256:digestBytes(unknown)}),
    /Unsupported prior receipt schema/);
});

test('durable receipt loader dispatches strict schemas and binds exact native predecessor bytes', async()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'pf-native-receipt-'));
  try {
    const receiptDir=path.join(directory,'release','receipts');
    fs.mkdirSync(receiptDir,{recursive:true});
    const previousFile=path.join(receiptDir,'4.35.0.json');
    const nativeFile=path.join(receiptDir,'4.36.0.json');
    const record=fixture().receipt;
    record.source.previousReceiptSha256=digestBytes(actualOldBytes);
    fs.writeFileSync(previousFile,actualOldBytes);
    fs.writeFileSync(nativeFile,JSON.stringify(record));
    assert.deepEqual(await loadReleaseReceipt('4.35.0',directory),old);
    assert.deepEqual(await loadReleaseReceipt('4.36.0',directory),record);
    assert.equal(await resolvePublishedPlatformSource('4.36.0',directory),record.platformSource);
    fs.writeFileSync(previousFile,Buffer.concat([actualOldBytes,Buffer.from('\n')]));
    await assert.rejects(loadReleaseReceipt('4.36.0',directory),/previous durable release receipt digest/i);
    fs.rmSync(previousFile);
    await assert.rejects(loadReleaseReceipt('4.36.0',directory),/missing previous durable release receipt/i);
    fs.writeFileSync(previousFile,actualOldBytes);
    for(const mutate of [
      x=>x.kind='project-forge-native-release-intent',
      x=>x.schemaVersion=99,
      x=>x.source.sourceRepository='private/fixture',
      x=>x.ci.nativeSourceMain.runAttempt=0,
      x=>x.publication.provenance.signed=false
    ]) {
      const invalid=structuredClone(record);mutate(invalid);
      fs.writeFileSync(nativeFile,JSON.stringify(invalid));
      await assert.rejects(loadReleaseReceipt('4.36.0',directory));
    }
    // A matching digest is not permission to use malformed prior facts.
    const wrong=structuredClone(old);
    wrong.publication.neutralNpxSmoke='unknown';
    const wrongBytes=Buffer.from(JSON.stringify(wrong));
    fs.writeFileSync(previousFile,wrongBytes);
    fs.writeFileSync(nativeFile,JSON.stringify({...record,source:{...record.source,
      previousReceiptSha256:digestBytes(wrongBytes)}}));
    await assert.rejects(loadReleaseReceipt('4.36.0',directory),/neutralNpxSmoke/);
  } finally {fs.rmSync(directory,{recursive:true,force:true});}
});
