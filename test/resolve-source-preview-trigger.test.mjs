import test from 'node:test';
import assert from 'node:assert/strict';
import { resolvePreviewTrigger } from '../scripts/resolve-source-preview-trigger.mjs';

const SHA='a'.repeat(40);
function issueRequest() {
  return {
    eventName: 'issues', repositoryOwner:'mriekki',
    event: {
      action: 'opened',
      sender: { login: 'mriekki' },
      issue: {
        title: '[project-forge-source-preview]',
        user: { login:'mriekki' },
        state:'open',
        body: JSON.stringify({
          sourceSha: SHA, sourceRunId: 12345,
          candidateMode: 'changed-feedback-4.36-preview'
        })
      }
    }
  };
}
function reject(fn, pattern) {
  const x=issueRequest();
  fn(x);
  assert.throws(()=>resolvePreviewTrigger(x),pattern);
}
test('owner-created Issue triggers only read-only unpublished preview',()=>{
  const x=resolvePreviewTrigger(issueRequest());
  assert.deepEqual(x,{sourceSha:SHA,sourceRunId:12345,candidateMode:'changed-feedback-4.36-preview'});
});
test('manual historical and new-mode dispatch remain supported',()=>{
  for(const mode of ['historical-4.35','changed-feedback-4.36-preview','versioned-assembly-fixture-preview']){
    const x=resolvePreviewTrigger({
      eventName:'workflow_dispatch', repositoryOwner:'mriekki',
      dispatch:{exact_source_sha:SHA,source_qualification_run_id:'12345',candidate_mode:mode}
    });
    assert.equal(x.candidateMode,mode);
  }
});
test('issue must be freshly opened by owner only',()=>{
  reject(x=>{x.event.issue.user.login='stranger';},/owner-authored/);
  reject(x=>{x.event.sender.login='other';},/owner-authored/);
  reject(x=>{x.event.action='edited';},/owner-authored/);
  reject(x=>{x.event.issue.state='closed';},/owner-authored/);
  reject(x=>{x.event.issue.title='[project-forge-publish]';},/owner-authored/);
  reject(x=>{x.repositoryOwner='other';},/owner-authored/);
});
test('unknown or publishing mode and extra field refused',()=>{
  reject(x=>{x.event.issue.body=JSON.stringify({sourceSha:SHA,sourceRunId:12345,candidateMode:'publish'});},
    /Unsupported or publishing/);
  reject(x=>{x.event.issue.body=JSON.stringify({sourceSha:SHA,sourceRunId:12345,candidateMode:'historical-4.35',approve:true});},
    /exactly/);
  reject(x=>{x.event.issue.body='not JSON';},/exact JSON/);
});
test('invalid or wrong source identity and run ID refused',()=>{
  reject(x=>{x.event.issue.body=JSON.stringify({sourceSha:'main',sourceRunId:12345,candidateMode:'historical-4.35'});},
    /exact immutable/);
  reject(x=>{x.event.issue.body=JSON.stringify({sourceSha:SHA,sourceRunId:0,candidateMode:'historical-4.35'});},
    /positive/);
  reject(x=>{x.event.issue.body=JSON.stringify({sourceSha:SHA,sourceRunId:1.5,candidateMode:'historical-4.35'});},
    /positive/);
});
test('other GitHub events are forbidden',()=>{
  assert.throws(()=>resolvePreviewTrigger({eventName:'push'}),/Unsupported/);
});

test('owner issue can select versioned fixture proof, not stable publication',()=>{
  const x=issueRequest();
  const b=JSON.parse(x.event.issue.body);
  b.candidateMode='versioned-assembly-fixture-preview';
  x.event.issue.body=JSON.stringify(b);
  assert.equal(resolvePreviewTrigger(x).candidateMode,b.candidateMode);
});
