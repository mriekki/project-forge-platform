import test from 'node:test';
import assert from 'node:assert/strict';
import {compareStableEvidence} from '../scripts/verify-selected-native-stable.mjs';

function fixture(){
  const sourceSha='a'.repeat(40), manifestSha='b'.repeat(64);
  const receiptSha='9541dd1b7db4208e8407f6148515aa9f9c39dc38fbaa018bd24bd48d04a58009';
  const ids=['authentication','core','deployment','feedback','release-notes'];
  const records=Object.fromEntries(ids.map((id,i)=>[id,{revision:String(i+1).repeat(40),
    revisionKind:'original-owner-git-commit',mappedInputSha256:String(i+1).repeat(64)}]));
  const prior={components:structuredClone(records)};
  prior.components.core.version='4.5.1';
  const selected={schemaVersion:2,kind:'project-forge-native-stable-candidate-assembly',
    package:'@mriekki/project-forge',version:'4.36.0',previousVersion:'4.35.0',
    previousReceiptSha256:receiptSha,sourceCommit:sourceSha,allowPublish:false,
    allowProduction:false,previousComponents:structuredClone(records)};
  const evidence={kind:'project-forge-native-stable-candidate-evidence',schemaVersion:2,
    sourceCommit:sourceSha,manifestSha256:manifestSha,packageVersion:'4.36.0',
    components:structuredClone(records),changedComponents:[],releaseAuthorized:false,
    previousAcceptanceAuthenticatedHere:false,sourceOwnershipTransferred:false,published:false,
    productionAuthorized:false,previousVersion:'4.35.0',previousReceiptSha256:receiptSha,
    archiveForm:'public-stable'};
  const projection={packageComponents:Object.fromEntries(ids.map(id=>[id,
    id==='core'?{revision:records[id].revision,version:'4.5.1'}:{revision:records[id].revision}])),
    assemblyRevisions:Object.fromEntries(ids.map(id=>[id,records[id].revision]))};
  return {sourceSha,manifestSha,prior,selected,evidence,projection};
}
test('first selected stable projection preserves identities without release authority',()=>{
  const proof=compareStableEvidence(fixture());
  assert.equal(proof.result,'SELECTED_STABLE_EVIDENCE_MATCH');
  for(const key of ['releaseAuthorized','published','sourceOwnershipTransferred','productionAuthorized'])
    assert.equal(proof[key],false);
});
test('first selected stable projection refuses drift, premature promotion and wrong prior selection',()=>{
  for(const mutate of [
    x=>x.selected.allowPublish=true,
    x=>x.selected.previousReceiptSha256='0'.repeat(64),
    x=>x.selected.version='4.36.0-preview.7',
    x=>x.selected.previousComponents.feedback.mappedInputSha256='0'.repeat(64),
    x=>x.evidence.archiveForm='private-rehearsal',
    x=>x.evidence.releaseAuthorized=true,
    x=>x.evidence.changedComponents=['feedback'],
    x=>x.evidence.manifestSha256='0'.repeat(64),
    x=>x.projection.packageComponents.core.version='9.0.0',
    x=>x.projection.assemblyRevisions.feedback='0'.repeat(40),
    x=>delete x.prior.components.deployment
  ]) {const input=fixture();mutate(input);assert.throws(()=>compareStableEvidence(input));}
});
