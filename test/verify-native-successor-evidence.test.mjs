import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {compareSuccessorEvidence} from '../scripts/verify-native-successor-evidence.mjs';

const ids=['authentication','core','deployment','feedback','release-notes'];
const sha=c=>c.repeat(40), digest=c=>c.repeat(64);
const pkg='@mriekki/project-forge';
function fixture({changed=[],nativePrior=false}={}) {
  const old=Object.fromEntries(ids.map((id,i)=>[id,{revision:sha(String(i+1)),
    revisionKind:'original-owner-git-commit',mappedInputSha256:digest(String(i+1))}]));
  if(nativePrior) old.feedback={revision:sha('a'),revisionKind:'private-monorepo-git-commit',
    mappedInputSha256:digest('a')};
  const prior={version:nativePrior?'4.36.1':'4.36.0',receiptSha256:digest('b'),
    components:structuredClone(old)};
  prior.components.core.version='4.5.1';
  const observed={targetVersion:nativePrior?'4.36.2':'4.36.1',sourceCommit:sha('c'),
    previousSourceCommit:sha('d'),historicalSourceCommit:sha('e'),shellTree:sha('f'),
    componentDigests:Object.fromEntries(ids.map(id=>[id,changed.includes(id)?digest('0'):old[id].mappedInputSha256])),
    coreVersion:changed.includes('core')?'4.5.2':'4.5.1'};
  const manifest={schemaVersion:2,kind:'project-forge-native-stable-candidate-assembly',package:pkg,
    version:observed.targetVersion,previousVersion:prior.version,previousReceiptSha256:prior.receiptSha256,
    sourceCommit:observed.sourceCommit,previousSourceCommit:observed.previousSourceCommit,
    historicalSourceCommit:observed.historicalSourceCommit,shellTree:observed.shellTree,
    previousComponents:old,allowPublish:false,allowProduction:false};
  const manifestBytes=Buffer.from(JSON.stringify(manifest));
  observed.manifestSha256=createHash('sha256').update(manifestBytes).digest('hex');
  const next=Object.fromEntries(ids.map(id=>[id,changed.includes(id)?
    {revision:observed.sourceCommit,revisionKind:'private-monorepo-git-commit',mappedInputSha256:digest('0')}:
    structuredClone(old[id])]));
  const evidence={schemaVersion:2,kind:'project-forge-native-stable-candidate-evidence',
    sourceCommit:observed.sourceCommit,manifestSha256:observed.manifestSha256,
    packageVersion:observed.targetVersion,components:next,changedComponents:[...changed].sort(),
    previousVersion:prior.version,previousReceiptSha256:prior.receiptSha256,archiveForm:'public-stable',
    releaseAuthorized:false,previousAcceptanceAuthenticatedHere:false,sourceOwnershipTransferred:false,
    published:false,productionAuthorized:false};
  const projection={package:{name:pkg,version:observed.targetVersion},
    packageComponents:Object.fromEntries(ids.map(id=>[id,id==='core'?
      {revision:next[id].revision,version:observed.coreVersion}:{revision:next[id].revision}])),
    assemblyRevisions:Object.fromEntries(ids.map(id=>[id,next[id].revision]))};
  return {manifestBytes,prior,observed,evidence,projection};
}
test('changed successor preserves unrelated original identities and derives only changed native identities',()=>{
  const input=fixture({changed:['core','feedback']});
  const result=compareSuccessorEvidence(input);
  assert.deepEqual(result.changedComponents,['core','feedback']);
  assert.equal(result.components.core.version,'4.5.2');
  assert.equal(result.components.feedback.revision,input.observed.sourceCommit);
  assert.deepEqual(result.components.deployment,input.prior.components.deployment);
  for(const key of ['releaseAuthorized','published','sourceOwnershipTransferred','productionAuthorized',
    'priorReceiptAuthenticatedHere','sourceEvidenceAuthenticatedHere']) assert.equal(result[key],false);
});
test('later successor preserves previously accepted native identity across unrelated source advances',()=>{
  const input=fixture({nativePrior:true});
  const result=compareSuccessorEvidence(input);
  assert.deepEqual(result.changedComponents,[]);
  assert.deepEqual(result.components,input.prior.components);
});
test('refuses unbound manifest and forged previous or current source observations',()=>{
  for(const mutate of [
    x=>x.manifestBytes[0]=0,
    x=>x.prior.receiptSha256=digest('9'),
    x=>x.observed.previousSourceCommit=sha('9'),
    x=>x.observed.shellTree=sha('9'),
    x=>x.observed.componentDigests.feedback=digest('9'),
    x=>x.observed.targetVersion=x.prior.version,
    x=>x.prior.components.feedback.revisionKind='unknown',
    x=>x.observed.coreVersion='4.99.0'
  ]) {const input=fixture();mutate(input);assert.throws(()=>compareSuccessorEvidence(input));}
});
test('refuses churn, hidden changes, wrong archive projection and premature authorization',()=>{
  for(const mutate of [
    x=>x.evidence.components.deployment.revision=x.observed.sourceCommit,
    x=>x.evidence.changedComponents=[],
    x=>x.evidence.releaseAuthorized=true,
    x=>x.evidence.previousAcceptanceAuthenticatedHere=true,
    x=>x.evidence.archiveForm='private-rehearsal',
    x=>x.projection.package.version='4.36.9',
    x=>x.projection.assemblyRevisions.feedback=sha('9'),
    x=>x.projection.packageComponents.core.version='4.9.9',
    x=>delete x.projection.packageComponents.authentication
  ]) {const input=fixture({changed:['feedback']});mutate(input);assert.throws(()=>compareSuccessorEvidence(input));}
});
