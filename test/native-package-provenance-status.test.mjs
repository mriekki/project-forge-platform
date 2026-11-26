import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {exactVersion,proofContext,projectProof,selectVersion} from '../scripts/native-package-provenance-status.mjs';

const receiptBytes=fs.readFileSync(new URL('../release/receipts/4.36.4.json',import.meta.url));
const receipt=JSON.parse(receiptBytes);
const version=receipt.package.version;
const env={GITHUB_REPOSITORY:'mriekki/project-forge-platform',GITHUB_SHA:'a'.repeat(40),
  GITHUB_REF:'refs/heads/main',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_RUN_ID:'12',GITHUB_RUN_ATTEMPT:'1'};
const verified={version,source:receipt.platformSource,runId:receipt.publication.workflowRunId,
  runAttempt:1,logIndex:receipt.publication.provenance.transparencyLogUrl.split('=')[1],
  archiveVerified:true,certificateVerified:true,publicationRunVerified:true,
  publicationAuthorized:false,productionAuthorized:false};
const input={receiptBytes,version,verified,env,observedAt:'2026-11-26T15:00:00.000Z'};

test('explicit exact version and PR stable selection are bounded',()=>{
  assert.equal(selectVersion({event:'workflow_dispatch',requested:version}),version);
  assert.equal(selectVersion({event:'pull_request',descriptor:{schemaVersion:1,channel:'stable',
    generation:{package:'@mriekki/project-forge',packageVersion:version}}}),version);
  for(const bad of ['latest','../4.36.4','4.36.4\nX=y','04.36.4','4.36.4-beta',''])assert.throws(()=>exactVersion(bad));
  assert.throws(()=>selectVersion({event:'push',requested:version}));
});
test('exact owner main proof and distinct PR preview context',()=>{
  assert.equal(proofContext(env).event,'workflow_dispatch');
  const preview=proofContext({...env,GITHUB_EVENT_NAME:'pull_request',GITHUB_REF:'refs/pull/12/merge'});
  assert.equal(preview.event,'pull_request');
  for(const change of [{GITHUB_REPOSITORY:'other/project-forge-platform'},{GITHUB_REF:'refs/heads/other'},
    {GITHUB_SHA:'main'},{GITHUB_RUN_ID:'0'},{GITHUB_RUN_ATTEMPT:'1.5'},{GITHUB_EVENT_NAME:'push'}]){
    assert.throws(()=>proofContext({...env,...change}));
  }
});
test('project exact canonical verifier result without issuing any authority',()=>{
  const result=projectProof(input);
  assert.equal(result.package.version,version);
  assert.equal(result.receiptSha256,createHash('sha256').update(receiptBytes).digest('hex'));
  assert.equal(result.archiveSha256,receipt.artifact.releaseCandidateSha256);
  assert.equal(result.platformSource,receipt.platformSource);
  assert.equal(result.publicationRunId,receipt.publication.workflowRunId);
  assert.equal(result.proofContext.runId,12);
  assert.equal(result.authorizesMutation,false);
  assert.equal(result.publicationAuthorized,false);
  assert.equal(result.productionAuthorized,false);
});
test('refuse mismatched result or any non-success or authority marker',()=>{
  for(const change of [{version:'4.36.3'},{source:'b'.repeat(40)},{runId:999},{runAttempt:0},
    {logIndex:'999'},{archiveVerified:false},{certificateVerified:false},
    {publicationRunVerified:false},{publicationAuthorized:true},{productionAuthorized:true}]){
    assert.throws(()=>projectProof({...input,verified:{...verified,...change}}));
  }
  assert.throws(()=>projectProof({...input,version:'4.36.3'}));
  assert.throws(()=>projectProof({...input,observedAt:'2026-02-30T12:00:00.000Z'}));
  assert.throws(()=>projectProof({...input,receiptBytes:Buffer.from('{"schemaVersion":2,"schemaVersion":2}')}));
});

test('actual verification job guard requires owner original actor and rerun initiator',()=>{
  const workflow=fs.readFileSync(new URL('../.github/workflows/native-package-provenance-status.yml',import.meta.url),'utf8');
  // Read the real folded job predicate. Pin its complete supported expression
  // before evaluating the common JS/Actions boolean subset on exact-case fixtures.
  const match=workflow.match(/^    if: >-\n((?: {6}[^\n]+\n)+)/m);
  assert.ok(match,'verification job predicate must be present');
  const guard=match[1].trim().split('\n').map(line=>line.trim()).join(' ');
  assert.equal(guard,
    "github.repository == 'mriekki/project-forge-platform' && "+
    "github.actor == github.repository_owner && "+
    "github.triggering_actor == github.repository_owner && "+
    "((github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main') || "+
    "(github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository))");
  const permits=new Function('github','return ('+guard+');');
  const owner='mriekki',repository=owner+'/project-forge-platform';
  const dispatch={repository,repository_owner:owner,actor:owner,triggering_actor:owner,
    event_name:'workflow_dispatch',ref:'refs/heads/main'};
  const preview={...dispatch,event_name:'pull_request',ref:'refs/pull/12/merge',
    event:{pull_request:{head:{repo:{full_name:repository}}}}};
  for(const context of [dispatch,preview]){
    assert.equal(permits(context),true);
    for(const change of [{actor:'collaborator'},{triggering_actor:'collaborator'},
      {triggering_actor:undefined},{repository:'other/project-forge-platform'}]){
      assert.equal(permits({...context,...change}),false);
    }
  }
  assert.equal(permits({...dispatch,ref:'refs/heads/work'}),false);
  assert.equal(permits({...dispatch,event_name:'push'}),false);
  assert.equal(permits({...preview,event:{pull_request:{head:{repo:{full_name:'other/fork'}}}}}),false);
});
