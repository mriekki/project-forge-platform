/**
 * Read-only comparison of exact native successor qualification run evidence.
 * All GitHub REST objects and logs must be retrieved by the protected caller
 * with the existing narrowly scoped source-read credential. The code pins
 * must come from an independently reviewed policy, never the source request,
 * private checkout, issue body or logs. No active trust policy is installed.
 */
import {isDeepStrictEqual as equal} from 'node:util';
import {strictJson} from './strict-json.mjs';

const SHA=/^[0-9a-f]{40}$/;
const REPO=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const WORKFLOW='.github/workflows/native-successor-main-qualification.yml';
const WORKFLOW_NAME='Native Exact-Main Successor Qualification (NO PUBLISH)';
const JOB='source-successor-qualification';
const positive=x=>Number.isSafeInteger(x)&&x>0;
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};
const exact=(x,p)=>typeof x==='string'&&p.test(x);
export const REQUIRED_CODE_PATHS=Object.freeze([
  WORKFLOW,
  'tools/release/resolve_successor_request.py',
  'tools/release/verify_main_identity.py',
  'tools/shared/verify_current_main_snapshot.py',
  'tools/npm/qualify_native_successor.py',
  'tools/npm/select_native_stable.py',
  'tools/npm/assemble_selected_stable.py',
  'tools/npm/build_manifest_preview.py',
  'tools/npm/preview_selected_manifest.py',
  'tools/npm/build_candidate.py',
  'tools/npm/build_versioned_preview.py',
  'tools/release/native_revision_plan.py',
  'tools/release/plan_component_revisions.py',
  'tests/release/generated_consumer_selected_proof.py'
]);
export const REQUIRED_STEPS=Object.freeze([
  'Checkout exact event main source',
  'Validate exact owner-issued nonpublishing successor request',
  'Observe authenticated current main without executing source code',
  'Verify authenticated current main and independent historical snapshots',
  'Checkout public reference only for immutable historical parity, never for build inputs',
  'Checkout public receipt verifier (read-only)',
  'Qualify immutable historical npm archive and consumer parity',
  'Checkout exact selected predecessor receipt and mirror',
  'Qualify exact current native successor and consumer rollback',
  'Qualify original Core, Bootstrap and Adoption Python contracts',
  'Setup Python 3.11 and test-only cryptographic dependencies',
  'Qualify Deployment restore/recovery and all original Python contracts',
  'Setup .NET 10 and verify Authentication, Feedback, Release Notes runtime',
  'Qualify Authentication .NET and household contracts',
  'Qualify Feedback fake-GitHub integration (no live provider)',
  'Qualify Release Notes Python, .NET, and UI contracts',
  'Reverify current main SHA after all source qualifications'
]);
function fields(value,keys,label){
  need(value&&typeof value==='object'&&!Array.isArray(value)&&
    equal(Object.keys(value).sort(),[...keys].sort()),'Invalid '+label);
}

export function verifySuccessorRunEvidence({policy,selected,repo,mainRef,run,jobs,code}) {
  fields(policy,['repository','repositoryId','workflowId','codePins'],'reviewed run policy');
  need(exact(policy.repository,REPO)&&positive(policy.repositoryId)&&positive(policy.workflowId),
    'Expected protected repository and workflow identity');
  fields(policy.codePins,REQUIRED_CODE_PATHS,'reviewed code pin inventory');
  for(const sha of Object.values(policy.codePins)) need(exact(sha,SHA),'Invalid reviewed code pin');
  fields(selected,['sourceCommit','workflowRunId','runAttempt'],'selected source run identity');
  need(exact(selected.sourceCommit,SHA)&&positive(selected.workflowRunId)&&positive(selected.runAttempt),
    'Exact selected source run/attempt required');
  need(repo?.full_name===policy.repository&&repo.id===policy.repositoryId&&
    repo.private===true&&repo.archived===false&&repo.default_branch==='main'&&positive(repo.owner?.id),
    'Protected source repository identity differs');
  need(mainRef?.ref==='refs/heads/main'&&mainRef.object?.type==='commit'&&
    mainRef.object.sha===selected.sourceCommit,'Authenticated current main differs');
  need(run?.id===selected.workflowRunId&&run.run_attempt===selected.runAttempt&&
    run.workflow_id===policy.workflowId&&run.path===WORKFLOW&&run.name===WORKFLOW_NAME&&
    run.head_sha===selected.sourceCommit&&run.head_branch==='main'&&run.event==='issues'&&
    run.status==='completed'&&run.conclusion==='success'&&
    run.repository?.id===policy.repositoryId&&run.head_repository?.id===policy.repositoryId&&
    run.actor?.id===repo.owner.id&&run.triggering_actor?.id===repo.owner.id&&
    Array.isArray(run.pull_requests)&&run.pull_requests.length===0,
    'Exact owner-issued successful successor run not established');
  fields(code,REQUIRED_CODE_PATHS,'authenticated code metadata inventory');
  for(const path of REQUIRED_CODE_PATHS){
    const file=code[path];
    need(file?.path===path&&file.type==='file'&&file.sha===policy.codePins[path],
      'Reviewed successor qualification code differs');
  }
  need(jobs?.total_count===1&&Array.isArray(jobs.jobs)&&jobs.jobs.length===1,
    'Exactly one source successor qualification job required');
  const job=jobs.jobs[0];
  need(positive(job.id)&&job.name===JOB&&job.workflow_name===WORKFLOW_NAME&&
    job.run_id===run.id&&job.run_attempt===run.run_attempt&&
    job.head_sha===selected.sourceCommit&&job.head_branch==='main'&&
    job.status==='completed'&&job.conclusion==='success'&&Array.isArray(job.steps),
    'Exact successful successor job identity differs');
  let previous=0, last=-1;
  const names=new Set();
  for(const step of job.steps){
    need(positive(step.number)&&step.number>previous&&typeof step.name==='string'&&
      !names.has(step.name)&&step.status==='completed'&&step.conclusion==='success',
      'Failed, skipped, duplicate or reordered successor job step');
    previous=step.number; names.add(step.name);
  }
  for(const name of REQUIRED_STEPS){
    const index=job.steps.findIndex(s=>s.name===name);
    need(index>last,'Required successor qualification step missing or reordered');
    last=index;
  }
  return Object.freeze({result:'NATIVE_SUCCESSOR_RUN_EVIDENCE_MATCH',
    sourceCommit:selected.sourceCommit,sourceJobId:job.id,
    nativeSourceMain:{result:'success',workflowRunId:run.id,runAttempt:run.run_attempt},
    qualificationEvent:'issues',sourceEvidenceAuthenticatedHere:false,
    releaseAuthorized:false,publicationAuthorized:false,productionAuthorized:false});
}

// The caller must fetch the exact job log using the verified job ID, not an
// arbitrary attachment. Do not echo the log or include private locators in
// public output. Only a single exact final proof block is accepted.
export function extractSuccessorProof(log){
  need(typeof log==='string'&&Buffer.byteLength(log,'utf8')<=16*1024*1024,
    'Invalid source qualification log size');
  const lines=log.split(/\r?\n/).map(line=>line.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z /,''));
  const begin='PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_BEGIN';
  const end='PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_END';
  const starts=lines.flatMap((line,i)=>line===begin?[i]:[]);
  const stops=lines.flatMap((line,i)=>line===end?[i]:[]);
  need(starts.length===1&&stops.length===1&&stops[0]===starts[0]+2,
    'Unique exact final successor proof block required');
  const raw=lines[starts[0]+1];
  need(Buffer.byteLength(raw,'utf8')<=64*1024,'Invalid successor proof size');
  let proof;
  try{proof=strictJson(raw,64*1024);}catch{throw new Error('Malformed successor proof');}
  need(proof&&typeof proof==='object'&&!Array.isArray(proof)&&
    proof.kind==='project-forge-offline-native-successor-proof'&&proof.schemaVersion===1&&
    proof.releaseAuthorized===false&&proof.published===false&&proof.productionAuthorized===false,
    'Invalid nonauthorizing successor proof');
  // Full field-by-field comparison to independent candidate evidence is
  // mandatory in composeSuccessorIntent; log extraction is not authentication.
  return proof;
}

export function verifyReviewedHarness(log,review){
 need(typeof log==='string'&&Buffer.byteLength(log)<=16*1024*1024,'Invalid source qualification log size');
 const lines=log.split(/\r?\n/).map(line=>line.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z /,''));
 const begin='PROJECT_FORGE_NATIVE_SUCCESSOR_HARNESS_BEGIN',end='PROJECT_FORGE_NATIVE_SUCCESSOR_HARNESS_END';
 const starts=lines.flatMap((line,i)=>line===begin?[i]:[]),stops=lines.flatMap((line,i)=>line===end?[i]:[]);
 need(starts.length===1&&stops.length===1&&stops[0]===starts[0]+2&&
 lines[stops[0]+1]==='PROJECT_FORGE_NATIVE_SUCCESSOR_PROOF_BEGIN','Unique reviewed harness immediately before final proof required');
 need(equal(strictJson(lines[starts[0]+1],8192),review),'Exact independently reviewed harness differs');
 return true;
}
