import test from 'node:test';
import assert from 'node:assert/strict';
import {verifySuccessorRunEvidence,extractSuccessorProof,verifyReviewedHarness,REQUIRED_CODE_PATHS,REQUIRED_STEPS}
  from '../scripts/native-successor-run-evidence.mjs';

const sha='a'.repeat(40), name='Native Exact-Main Successor Qualification (NO PUBLISH)';
function fixture(){
  const policy={repository:'example/source',repositoryId:1,workflowId:2,
    codePins:Object.fromEntries(REQUIRED_CODE_PATHS.map(p=>[p,'b'.repeat(40)]))};
  const selected={sourceCommit:sha,workflowRunId:3,runAttempt:2};
  const repo={full_name:policy.repository,id:1,private:true,archived:false,
    default_branch:'main',owner:{id:4}};
  const run={id:3,run_attempt:2,workflow_id:2,path:REQUIRED_CODE_PATHS[0],name,
    head_sha:sha,head_branch:'main',event:'issues',status:'completed',conclusion:'success',
    repository:{id:1},head_repository:{id:1},actor:{id:4},triggering_actor:{id:4},pull_requests:[]};
  const job={id:5,name:'source-successor-qualification',workflow_name:name,run_id:3,
    run_attempt:2,head_sha:sha,head_branch:'main',status:'completed',conclusion:'success',
    steps:['Set up job',...REQUIRED_STEPS,'Complete job'].map((name,i)=>({
      name,number:i+1,status:'completed',conclusion:'success'}))};
  return {policy,selected,repo,run,jobs:{total_count:1,jobs:[job]},
    mainRef:{ref:'refs/heads/main',object:{type:'commit',sha}},
    code:Object.fromEntries(REQUIRED_CODE_PATHS.map(path=>[path,{path,type:'file',sha:policy.codePins[path]}]))};
}
test('exact independently retrieved successor run/attempt, code pins and ordered steps match without authority',()=>{
  const x=fixture(),result=verifySuccessorRunEvidence(x);
  assert.deepEqual(result.nativeSourceMain,{result:'success',workflowRunId:3,runAttempt:2});
  assert.equal(result.sourceJobId,5);
  for(const k of ['sourceEvidenceAuthenticatedHere','releaseAuthorized','publicationAuthorized','productionAuthorized'])
    assert.equal(result[k],false);
});
test('reject stale main, wrong owner, wrong run, wrong job, unreviewed code and incomplete step evidence',()=>{
  for(const mutate of [
    x=>x.repo.id=99,x=>x.repo.private=false,x=>x.repo.archived=true,
    x=>x.mainRef.object.sha='0'.repeat(40),x=>x.run.actor.id=99,
    x=>x.run.triggering_actor.id=99,x=>x.run.head_repository.id=99,
    x=>x.run.run_attempt=1,x=>x.run.workflow_id=99,x=>x.run.event='pull_request',
    x=>x.run.pull_requests=[{}],x=>x.run.conclusion='failure',x=>x.run.path='.github/workflows/other.yml',
    x=>x.jobs.total_count=2,x=>x.jobs.jobs[0].run_attempt=1,
    x=>x.jobs.jobs[0].head_sha='0'.repeat(40),
    x=>x.jobs.jobs[0].steps[3].conclusion='skipped',
    x=>x.jobs.jobs[0].steps.splice(3,1),
    x=>{const s=x.jobs.jobs[0].steps;[s[3].name,s[4].name]=[s[4].name,s[3].name];},
    x=>x.jobs.jobs[0].steps[3].name=x.jobs.jobs[0].steps[2].name,
    x=>x.code[REQUIRED_CODE_PATHS[1]].sha='0'.repeat(40),
    x=>delete x.policy.codePins[REQUIRED_CODE_PATHS[1]],
    x=>delete x.code[REQUIRED_CODE_PATHS[2]]
  ]) {const x=fixture();mutate(x);assert.throws(()=>verifySuccessorRunEvidence(x));}
});
test('extract one exact final proof block without treating command echoes as proof',()=>{
  const p={schemaVersion:1,kind:'project-forge-offline-native-successor-proof',
    releaseAuthorized:false,published:false,productionAuthorized:false};
  const begin='PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_BEGIN',end='PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_END';
  const stamp='2026-01-01T00:00:00.1234567Z ';
  const log=['echo '+begin,'echo '+end,begin,JSON.stringify(p),end].map(l=>stamp+l).join('\n');
  assert.deepEqual(extractSuccessorProof(log),p);
  for(const altered of [log+'\n'+begin,log+'\n'+end,log.replace(JSON.stringify(p),'not-json'),
    log.replace(JSON.stringify(p),JSON.stringify({...p,published:true})),
    log.replace(stamp+end,stamp+'extra\n'+stamp+end),'echo '+begin+'\n'+JSON.stringify(p)+'\n'+end
  ])assert.throws(()=>extractSuccessorProof(altered));
});

test('reviewed harness binds exact selected tree, run, predecessor and trace',()=>{
 const h={sourceCommit:sha,tree:'b'.repeat(40),workflowRunId:3,runAttempt:2,qualificationIssue:4,previousPlatformCommit:'c'.repeat(40),manifestSha256:'d'.repeat(64),candidateSha256:'e'.repeat(64)};
 const log=['PROJECT_FORGE_NATIVE_SUCCESSOR_HARNESS_BEGIN',JSON.stringify(h),'PROJECT_FORGE_NATIVE_SUCCESSOR_HARNESS_END','PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_BEGIN'].join('\n');
 assert.equal(verifyReviewedHarness(log,h),true);
 assert.throws(()=>verifyReviewedHarness(log,{...h,tree:'f'.repeat(40)}));
 assert.throws(()=>verifyReviewedHarness(log+'\nPROJECT_FORGE_NATIVE_SUCCESSOR_HARNESS_BEGIN',h));
 assert.throws(()=>verifyReviewedHarness(log.replace('PROOF_BEGIN','UNREVIEWED'),h));
});
