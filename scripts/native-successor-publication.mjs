/** Repeatable exact successor publication evidence, not a second publisher.
 * The isolated public preview authenticates and rebuilds the private source.
 * The publisher verifies that completed run, exact reviewed selection, registry
 * predecessor, and byte-identical current public mirror. No candidate source
 * code or private token is needed in the OIDC job.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {qualifyPriorProvenance} from './verify-native-publication-provenance.mjs';
import {isDeepStrictEqual as equal} from 'node:util';
import {pathToFileURL} from 'node:url';
import {strictJson} from './strict-json.mjs';
import {validateNativeReceipt,constructNativeIntent,validateNativeIntent,constructNativeReceiptFromIntent} from './native-source-receipt.mjs';
import {readReleaseArchiveProjection} from './prior-registry-archive.mjs';
import {verifyNativeStableCandidate} from './native-stable-candidate-verifier.mjs';
import {selectPlatformRun,verifyRegistryVersion} from './first-native-publication.mjs';

const PKG='@mriekki/project-forge';
const PLATFORM_ID=1420848802, OWNER_ID=12054121;
const SHA=/^[0-9a-f]{40}$/, DIGEST=/^[0-9a-f]{64}$/, VERSION=/^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$/;
const SIGSTORE=/^https:\/\/search\.sigstore\.dev\/\?logIndex=[0-9]+$/;
const ids=['authentication','core','deployment','feedback','release-notes'];
const PREVIEW_PATH='.github/workflows/native-successor-admission-preview.yml';
const PREVIEW_NAME='Native Successor Admission Preview (NO RELEASE)';
const PREVIEW_JOB='successor-preview-only';
export const PREVIEW_CODE_PATHS=Object.freeze([
 PREVIEW_PATH,'scripts/native-successor-admission-preview.mjs','scripts/native-successor-run-evidence.mjs',
 'scripts/prior-registry-archive.mjs','scripts/prior-release-projection.mjs','scripts/release-receipt.mjs',
 'scripts/native-source-receipt.mjs','scripts/verify-native-successor-evidence.mjs','scripts/verify-assets.mjs',
 'scripts/verify-native-publication-provenance.mjs','scripts/strict-json.mjs',
 'src/package-data.mjs','src/engine.mjs','src/passkey-capability.mjs'
]);
const PREVIEW_STEPS=[
 'Checkout exact reviewed public Platform',
 'Confirm exact native archive pack client and install separate signature client',
 'Resolve exact owner-selected nonpublishing successor',
 'Collect authenticated source CI run and pinned code',
 'Checkout independently compared exact private source (read only)',
 'Verify reviewed assembly code and clean exact checkout',
 'Verify exact predecessor receipt and public registry signature',
 'Independently derive selection, observations and candidate archive (NO PUBLISH)',
 'Recheck authenticated private and public main after preview'
];
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};
const positive=x=>Number.isSafeInteger(x)&&x>0;
const exact=(x,p)=>typeof x==='string'&&p.test(x);
const hash=b=>createHash('sha256').update(b).digest('hex');
const fields=(x,keys,label)=>need(x&&typeof x==='object'&&!Array.isArray(x)&&
 equal(Object.keys(x).sort(),[...keys].sort()),'Invalid '+label);
const scratch=n=>path.join(process.env.RUNNER_TEMP,n);
const read=n=>fs.readFileSync(scratch(n));
const json=n=>JSON.parse(read(n));
const save=(n,x)=>fs.writeFileSync(scratch(n),JSON.stringify(x)+'\n',{flag:'wx',mode:0o600});
function parse(raw){need(typeof raw==='string'&&Buffer.byteLength(raw)<=64*1024,'Bounded JSON required');return strictJson(raw,64*1024);}
function advances(a,b){if(!exact(a,VERSION)||!exact(b,VERSION))return false;
 const x=a.split('.').map(Number),y=b.split('.').map(Number);
 for(let i=0;i<3;i++)if(x[i]!==y[i])return x[i]>y[i];return false;}
function selectedSource(s){
 fields(s,['sourceCommit','workflowRunId','runAttempt','previousVersion','previousReceiptSha256',
 'version','manifestSha256','candidateSha256'],'source selection');
 need(exact(s.sourceCommit,SHA)&&positive(s.workflowRunId)&&positive(s.runAttempt)&&
 [s.previousReceiptSha256,s.manifestSha256,s.candidateSha256].every(v=>exact(v,DIGEST))&&
 advances(s.version,s.previousVersion)&&(s.previousVersion==='4.36.0'||advances(s.previousVersion,'4.36.0')),
 'Invalid stable successor selection');
 return s;
}
export function validateSelection(s){
 fields(s,['schemaVersion','kind','source','preview'],'reviewed publication selection');
 need(s.schemaVersion===1&&s.kind==='project-forge-reviewed-native-successor-selection','Invalid selection kind');
 selectedSource(s.source);
 fields(s.preview,['platformCommit','workflowId','runId','runAttempt'],'preview identity');
 need(exact(s.preview.platformCommit,SHA)&&[s.preview.workflowId,s.preview.runId,s.preview.runAttempt].every(positive),
 'Invalid exact admission run selection');
 return s;
}
export function resolveSuccessorPublication({event,owner,platformSha,currentRunId,selectionBytes}){
 need(typeof owner==='string'&&owner.length>0&&event?.action==='opened'&&event.issue?.state==='open'&&
 event.issue.user?.login===owner&&event.sender?.login===owner&&positive(currentRunId)&&exact(platformSha,SHA),
 'Exact owner publication issue required');
 need(Buffer.isBuffer(selectionBytes)&&selectionBytes.length>0&&selectionBytes.length<=64*1024,
 'Reviewed selection missing');
 const selection=validateSelection(parse(selectionBytes.toString('utf8')));
 const version=selection.source.version;
 const title=event.issue.title;
 const mode=title==='[project-forge-native-successor-publish] '+version?'publish':
 title==='[project-forge-native-successor-publish-verify] '+version?'verify':null;
 need(mode,'Unknown successor publication request');
 const r=parse(event.issue.body);
 fields(r,['version','platformCommit','selectionSha256',...(mode==='verify'?['publicationRunId','publicationRunAttempt','provenanceUrl']:[])],
 'exact owner publication request');
 need(r.version===version&&r.platformCommit===platformSha&&r.selectionSha256===hash(selectionBytes),
 'Owner request differs from reviewed current selection');
 if(mode==='verify')need(positive(r.publicationRunId)&&positive(r.publicationRunAttempt)&&
 r.publicationRunId!==currentRunId&&exact(r.provenanceUrl,SIGSTORE),'Exact original publication required');
 return {mode,version,platformCommit,selectionSha256:r.selectionSha256,
  publicationRunId:mode==='publish'?currentRunId:r.publicationRunId,
  publicationRunAttempt:mode==='publish'?null:r.publicationRunAttempt,
  provenanceUrl:mode==='verify'?r.provenanceUrl:'',selection};
}
function exactRun(run,{id,attempt,commit,workflowId,workflowPath,workflowName,success}){
 need(run?.id===id&&run.run_attempt===attempt&&run.head_sha===commit&&run.path===workflowPath&&
 (!workflowId||run.workflow_id===workflowId)&&(!workflowName||run.name===workflowName)&&
 run.head_branch==='main'&&run.event==='issues'&&run.status==='completed'&&
 (!success||run.conclusion==='success')&&run.repository?.id===PLATFORM_ID&&run.head_repository?.id===PLATFORM_ID&&
 run.actor?.id===OWNER_ID&&run.triggering_actor?.id===OWNER_ID&&Array.isArray(run.pull_requests)&&run.pull_requests.length===0,
 'Exact authenticated public workflow run differs');
}
function exactJob(jobs,run,name,success){
 need(Array.isArray(jobs?.jobs)&&jobs.total_count===jobs.jobs.length,'Complete attempt job inventory required');
 const found=jobs.jobs.filter(j=>j.name===name);
 need(found.length===1,'Exact public job missing');
 const j=found[0];
 need(positive(j.id)&&j.run_id===run.id&&j.run_attempt===run.run_attempt&&j.head_sha===run.head_sha&&
 j.head_branch==='main'&&j.status==='completed'&&(!success||j.conclusion==='success')&&Array.isArray(j.steps),
 'Exact completed public job differs');
 return j;
}
function orderedSteps(job,names){
 let prev=-1;
 for(const name of names){
  const found=job.steps.filter(x=>x.name===name);
  need(found.length===1&&found[0].status==='completed'&&found[0].conclusion==='success'&&
   positive(found[0].number)&&found[0].number>prev,'Required successful step missing or reordered');
  prev=found[0].number;
 }
}
function logLines(log){
 need(typeof log==='string'&&Buffer.byteLength(log)<=16*1024*1024,'Invalid exact job log');
 return log.split(/\r?\n/).map(l=>l.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z /,''));
}
function uniqueBlock(log,begin,end){
 const lines=logLines(log),starts=lines.flatMap((l,i)=>l===begin?[i]:[]),stops=lines.flatMap((l,i)=>l===end?[i]:[]);
 need(starts.length===1&&stops.length===1&&stops[0]===starts[0]+2,'Unique exact witness required');
 return parse(lines[starts[0]+1]);
}
export function verifyAdmissionWitness({selection,run,jobs,log,unchangedReviewedCode}){
 validateSelection(selection);
 const p=selection.preview;
 exactRun(run,{id:p.runId,attempt:p.runAttempt,commit:p.platformCommit,workflowId:p.workflowId,
 workflowPath:PREVIEW_PATH,workflowName:PREVIEW_NAME,success:true});
 need(unchangedReviewedCode===true&&jobs.total_count===1,'Reviewed admission code must be identical or rerun admission');
 const job=exactJob(jobs,run,PREVIEW_JOB,true);
 orderedSteps(job,PREVIEW_STEPS);
 const w=uniqueBlock(log,'PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_BEGIN','PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_END');
 fields(w,['schemaVersion','kind','selection','platformCommit','previewRunId','previewRunAttempt',
 'priorComponentDigests','componentDigests','previousSourceCommit','changedComponents','releaseAuthorized','published','productionAuthorized'],
 'admission witness');
 need(w.schemaVersion===1&&w.kind==='project-forge-successor-admission-witness'&&equal(w.selection,selection.source)&&
 w.platformCommit===p.platformCommit&&w.previewRunId===p.runId&&w.previewRunAttempt===p.runAttempt&&
 exact(w.previousSourceCommit,SHA)&&w.releaseAuthorized===false&&w.published===false&&w.productionAuthorized===false,
 'Witness differs from selected nonpublishing evidence');
 for(const d of [w.priorComponentDigests,w.componentDigests]){
  fields(d,ids,'component digest inventory');
  need(Object.values(d).every(v=>exact(v,DIGEST)),'Invalid mapped digest');
 }
 need(equal(w.changedComponents,ids.filter(id=>w.componentDigests[id]!==w.priorComponentDigests[id])),
 'Changed component witness differs');
 const lines=logLines(log);
 const end=lines.indexOf('PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_END');
 need(lines.filter(l=>l==='NATIVE_SUCCESSOR_PREVIEW_COMPLETE RELEASE_AUTHORIZED=false NPM_PUBLISHED=false PRODUCTION_CHANGED=false').length===1&&
 lines.indexOf('NATIVE_SUCCESSOR_PREVIEW_COMPLETE RELEASE_AUTHORIZED=false NPM_PUBLISHED=false PRODUCTION_CHANGED=false')>end,
 'Final successful source/public recheck evidence missing');
 return w;
}
export function verifyRecoveryRun({request,run,jobs,log}){
 need(request.mode==='verify','Recovery-only evidence required');
 exactRun(run,{id:request.publicationRunId,attempt:request.publicationRunAttempt,commit:request.platformCommit,
 workflowPath:'.github/workflows/npm-publish.yml',workflowName:'Publish npm Package',success:false});
 const job=exactJob(jobs,run,'native-successor-publish',false);
 orderedSteps(job,['Publish exact successor archive through existing trusted publisher']);
 const lines=logLines(log);
 need(lines.filter(l=>l==='NATIVE_SUCCESSOR_PUBLISHED_PROVENANCE_URL='+request.provenanceUrl).length===1,
 'Exact original signed provenance location missing');
 return true;
}
export function requireRegistryState({mode,targetStatus,latest,previousVersion,version}){
 need(mode==='publish'?targetStatus===404&&latest===previousVersion:
 mode==='verify'&&targetStatus===200&&latest===version,'Registry state does not match explicit publication/recovery mode');
}
export function prepareSuccessor({request,witness,priorReceiptBytes,priorArchive,priorRegistry,mirrorArchive,platformRuns}){
 const s=request.selection.source;
 const prior=validateNativeReceipt(JSON.parse(priorReceiptBytes),s.previousVersion);
 need(hash(priorReceiptBytes)===s.previousReceiptSha256&&prior.source.commit===witness.previousSourceCommit,
 'Exact accepted predecessor differs');
 // The admission witness independently recomputed both digests and checked
 // the candidate against the exact predecessor receipt/archive.
 const records=Object.fromEntries(ids.map(id=>{
  const old=prior.components[id],d=witness.componentDigests[id];
  need(old.mappedInputSha256===witness.priorComponentDigests[id],'Prior mapped digest differs');
  return [id,d===old.mappedInputSha256?structuredClone(old):{
   revision:s.sourceCommit,revisionKind:'private-monorepo-git-commit',mappedInputSha256:d,
   ...(id==='core'?{version:null}:{})
  }];
 }));
 // Core compatibility version is read from the exact byte-identical mirror.
 // Do not derive it from a user-supplied request.
 const coreVersion=readReleaseArchiveProjection({archiveBytes:mirrorArchive,expectedVersion:s.version,requirePublishableForm:true}).packageComponents.core.version;
 if(witness.changedComponents.includes('core'))records.core.version=coreVersion;
 const nativeSourceMain={result:'success',workflowRunId:s.workflowRunId,runAttempt:s.runAttempt};
 const platformMain=selectPlatformRun(platformRuns,request.platformCommit);
 const intent=constructNativeIntent({
  package:{name:PKG,version:s.version},platformSource:request.platformCommit,
  source:{mode:'native-monorepo',commit:s.sourceCommit,previousVersion:s.previousVersion,
  previousReceiptSha256:s.previousReceiptSha256,manifestSha256:s.manifestSha256,qualificationEvent:'issues'},
  components:records,ci:{nativeSourceMain,platformMain},candidateSha256:s.candidateSha256
 });
 verifyNativeStableCandidate({intent,prior:{receiptBytes:priorReceiptBytes,archiveBytes:priorArchive,
  registry:priorRegistry,platformSource:prior.platformSource,componentDigests:witness.priorComponentDigests},
  candidateArchiveBytes:mirrorArchive,observedSource:{platformSource:request.platformCommit,
  sourceCommit:s.sourceCommit,manifestSha256:s.manifestSha256,qualificationEvent:'issues',
  nativeSourceMain,platformMain,componentDigests:witness.componentDigests}});
 return intent;
}
export function finalizeSuccessor({intent,mirror,registryArchive,registry,times,publicationRunId,provenanceUrl}){
 validateNativeIntent(intent);
 need(Buffer.isBuffer(mirror)&&mirror.equals(registryArchive)&&hash(mirror)===intent.candidateSha256,
 'Exact registry archive differs from admitted mirror');
 const artifact=verifyRegistryVersion(registry,mirror,intent.package.version);
 const time=times[intent.package.version];
 need(exact(time,/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/),'Exact publication time missing');
 return constructNativeReceiptFromIntent(intent,{artifact,publication:{publishedAt:time.replace(/\.\d{3}Z$/,'Z'),
 workflowRunId:publicationRunId,publisher:'github-oidc',registryIdentity:'verified',neutralNpxSmoke:'verified',
 provenance:{signed:true,transparencyLogUrl:provenanceUrl}}});
}
function output(x){fs.appendFileSync(process.env.GITHUB_OUTPUT,Object.entries(x).map(([k,v])=>k+'='+v+'\n').join(''));}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  switch(process.argv[2]){
   case 'request':{
    const version=JSON.parse(fs.readFileSync('package.json','utf8')).version;
    need(exact(version,VERSION),'Exact stable mirror version required');
    const r=resolveSuccessorPublication({event:JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH,'utf8')),
      owner:process.env.REPOSITORY_OWNER,platformSha:process.env.GITHUB_SHA,
      currentRunId:Number(process.env.GITHUB_RUN_ID),selectionBytes:fs.readFileSync('release/native-selections/'+version+'.json')});
    save('pf-successor-publish-request.json',r);
    output({mode:r.mode,version:r.version,platformCommit:r.platformCommit,publicationRunId:r.publicationRunId,
      publicationRunAttempt:r.publicationRunAttempt??'',provenanceUrl:r.provenanceUrl,
      sourceCommit:r.selection.source.sourceCommit,previousVersion:r.selection.source.previousVersion,
      previousReceiptSha256:r.selection.source.previousReceiptSha256,candidateSha256:r.selection.source.candidateSha256,
      previewCommit:r.selection.preview.platformCommit,previewRunId:r.selection.preview.runId,
      previewAttempt:r.selection.preview.runAttempt});
    break;
   }
   case 'preview-job':{
    const r=json('pf-successor-publish-request.json'),run=json('pf-successor-preview-run.json'),jobs=json('pf-successor-preview-jobs.json');
    const p=r.selection.preview;
    exactRun(run,{id:p.runId,attempt:p.runAttempt,commit:p.platformCommit,workflowId:p.workflowId,
     workflowPath:PREVIEW_PATH,workflowName:PREVIEW_NAME,success:true});
    const j=exactJob(jobs,run,PREVIEW_JOB,true);
    output({jobId:j.id});break;
   }
   case 'code-paths':console.log(PREVIEW_CODE_PATHS.join('\n'));break;
   case 'prepare':{
    const r=json('pf-successor-publish-request.json');
    const witness=verifyAdmissionWitness({selection:r.selection,run:json('pf-successor-preview-run.json'),
     jobs:json('pf-successor-preview-jobs.json'),log:read('pf-successor-preview.log').toString('utf8'),
     unchangedReviewedCode:process.env.PREVIEW_CODE_IDENTICAL==='true'});
    requireRegistryState({mode:r.mode,targetStatus:Number(process.env.TARGET_HTTP_STATUS),
     latest:json('pf-successor-latest.json').version,previousVersion:r.selection.source.previousVersion,version:r.version});
    const intent=prepareSuccessor({request:r,witness,priorReceiptBytes:read('pf-successor-prior-receipt.json'),
     priorArchive:read('pf-successor-prior.tgz'),priorRegistry:json('pf-successor-prior-registry.json'),
     mirrorArchive:read('pf-successor-mirror.tgz'),platformRuns:json('pf-successor-platform-ci.json')});
    save('pf-successor-intent.json',intent);
    console.log('Exact independent successor admission, prior acceptance and public mirror matched.');
    output({intent:JSON.stringify(intent)});break;
   }
   case 'recovery-job':{
    const r=json('pf-successor-publish-request.json'),run=json('pf-successor-original-run.json'),jobs=json('pf-successor-original-jobs.json');
    exactRun(run,{id:r.publicationRunId,attempt:r.publicationRunAttempt,commit:r.platformCommit,
     workflowPath:'.github/workflows/npm-publish.yml',workflowName:'Publish npm Package',success:false});
    output({jobId:exactJob(jobs,run,'native-successor-publish',false).id});break;
   }
   case 'recovery':verifyRecoveryRun({request:json('pf-successor-publish-request.json'),
    run:json('pf-successor-original-run.json'),jobs:json('pf-successor-original-jobs.json'),log:read('pf-successor-original.log').toString('utf8')});break;
   case 'finalize':{
    const intent=validateNativeIntent(parse(process.env.INTENT));
    const receipt=finalizeSuccessor({intent,mirror:read('pf-successor-mirror.tgz'),registryArchive:read('pf-successor-registry.tgz'),
     registry:json('pf-successor-registry.json'),times:json('pf-successor-times.json'),
     publicationRunId:Number(process.env.PUBLICATION_RUN_ID),provenanceUrl:process.env.PROVENANCE_URL});
    const neutral=scratch('pf-successor-neutral');
    await qualifyPriorProvenance({receipt,registry:json('pf-successor-registry.json'),archive:read('pf-successor-registry.tgz'),
      times:json('pf-successor-times.json'),lock:JSON.parse(fs.readFileSync(path.join(neutral,'package-lock.json'))),
      npmRoot:scratch('pf-signature-client/node_modules/npm')});
    // Execute package CLI only AFTER authentication; never pass credentials.
    const smokeEnv={PATH:process.env.PATH,HOME:neutral,LANG:'C',NODE_ENV:'production'};
    need(execFileSync(path.join(neutral,'node_modules/.bin/project-forge'),['version'],
      {cwd:neutral,env:smokeEnv,encoding:'utf8',timeout:30000,stdio:['ignore','pipe','pipe']}).trim()===
      PKG+' '+intent.package.version,'Exact verified neutral CLI version differs');
    save('publication-evidence.json',receipt);
    console.log('PROJECT_FORGE_NATIVE_PUBLICATION_EVIDENCE_BEGIN');
    console.log(JSON.stringify(receipt));
    console.log('PROJECT_FORGE_NATIVE_PUBLICATION_EVIDENCE_END');break;
   }
   default:throw new Error('Unknown successor publication operation');
  }
 }catch(e){console.error('Native successor publication evidence refused: '+e.message);process.exitCode=2;}
}
