/** Explicit first native release authorization; no implicit or floating version. */
import {isDeepStrictEqual as equal} from 'node:util';
import {readFileSync,appendFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
export const VERSION='4.36.0';
export const SOURCE='14415666dd8b698f540f8f68f82971ea17884374';
export const CANDIDATE_SHA='d098f7ff91e6c051f229961ea0458e9c4519f55b682bb1103ddb2fb27f8d46b4';
export const SOURCE_RUN=44954708158;
export const ADMISSION_RUN=44962439172;
export const ADMISSION_PLATFORM='5aa9580a5c21d2d8039c1fdad0203135236a95b1';
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};
const positive=x=>Number.isSafeInteger(x)&&x>0;
export function resolveNativePublish({event,owner,platformSha,currentRunId}) {
  need(typeof owner==='string'&&owner.length>0&&event?.action==='opened'&&
    event.issue?.state==='open'&&event.issue.user?.login===owner&&event.sender?.login===owner,
    'Exact owner-opened native publication issue required');
  need(positive(currentRunId),'Exact current workflow ID required');
  const title=event.issue.title;
  const mode=title==='[project-forge-native-publish] '+VERSION?'publish':
    title==='[project-forge-native-publish-verify] '+VERSION?'verify':null;
  need(mode!==null,'Unknown native publication request');
  const request=JSON.parse(event.issue.body);
  const keys=['version','sourceCommit','candidateSha256',...(mode==='verify'?['publicationRunId','provenanceUrl']:[])];
  need(request&&typeof request==='object'&&!Array.isArray(request)&&
    equal(Object.keys(request).sort(),keys.sort()),'Unexpected native publication request fields');
  need(request.version===VERSION&&request.candidateSha256===CANDIDATE_SHA&&
    /^[0-9a-f]{40}$/.test(platformSha)&&request.sourceCommit===platformSha,
    'Native release request differs from reviewed version, archive or Platform commit');
  if(mode==='verify')need(positive(request.publicationRunId)&&request.publicationRunId!==currentRunId&&
    typeof request.provenanceUrl==='string'&&/^https:\/\/search\.sigstore\.dev\/\?logIndex=[0-9]+$/.test(request.provenanceUrl),
    'Exact original publication evidence required');
  return {mode,version:VERSION,sourceCommit:platformSha,candidateSha256:CANDIDATE_SHA,
    publicationRunId:mode==='publish'?currentRunId:request.publicationRunId,
    provenanceUrl:mode==='verify'?request.provenanceUrl:''};
}
export function verifyAdmissionRun(run,jobs) {
  need(run?.id===ADMISSION_RUN&&run.run_attempt===1&&run.head_sha===ADMISSION_PLATFORM&&
    run.head_branch==='main'&&run.path==='.github/workflows/p0-monorepo-source-preview.yml'&&
    run.event==='issues'&&run.status==='completed'&&run.conclusion==='success'&&
    run.repository?.id===1420848802&&run.actor?.id===12054121&&run.triggering_actor?.id===12054121,
    'Exact independent candidate admission run not verified');
  const job=jobs?.jobs?.[0];
  need(jobs?.total_count===1&&jobs.jobs.length===1&&job.name==='untrusted-preview-only'&&
    job.run_id===run.id&&job.run_attempt===1&&job.status==='completed'&&job.conclusion==='success',
    'Exact independent admission job not verified');
  for(const name of ['Collect authenticated private source and exact release CI evidence',
    'Retrieve reviewed stable selection (read only)','Independently assemble and verify first stable candidate (NO PUBLISH)',
    'Recheck authenticated private main after candidate verification']) {
    const matches=job.steps.filter(s=>s.name===name);
    need(matches.length===1&&matches[0].conclusion==='success','Independent candidate admission step missing');
  }
}
export function verifyOriginalNativeRun(run,jobs,{publicationRunId,sourceCommit}) {
  need(run?.id===publicationRunId&&run.head_sha===sourceCommit&&run.head_branch==='main'&&
    run.path==='.github/workflows/npm-publish.yml'&&run.event==='issues'&&
    run.repository?.id===1420848802&&run.actor?.id===12054121&&run.triggering_actor?.id===12054121&&
    run.status==='completed','Original native publication run differs');
  const found=jobs?.jobs?.filter(j=>j.name==='native-publish')??[];
  need(found.length===1&&found[0].run_id===run.id&&found[0].run_attempt===run.run_attempt,
    'Original native publication job differs');
  const matches=found[0].steps.filter(s=>s.name==='Publish verified native archive with existing npm trusted publisher');
  need(matches.length===1&&matches[0].conclusion==='success','Original verified publish step did not succeed');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {
    const r=resolveNativePublish({event:JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH,'utf8')),
      owner:process.env.REPOSITORY_OWNER,platformSha:process.env.GITHUB_SHA,currentRunId:Number(process.env.GITHUB_RUN_ID)});
    appendFileSync(process.env.GITHUB_OUTPUT,
      Object.entries(r).map(([k,v])=>k+'='+v+'\n').join(''));
  } catch {console.error('Native publication authorization refused');process.exitCode=2;}
}
