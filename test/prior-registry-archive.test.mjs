import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { verifyPriorRegistryArchive } from '../scripts/prior-registry-archive.mjs';
import { verifyReleasedContractAlignment } from '../scripts/native-release-contract-alignment.mjs';

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
      'package.json':{...receipt.package},
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
