/** One-use owner approval. Workflow-wide concurrency serializes claims.
 * No OIDC here. An uncertain consumption or registry result holds the release.
 */
import {isDeepStrictEqual as equal} from 'node:util';
import {execFileSync} from 'node:child_process';
import {strictJson} from './strict-json.mjs';
import {pathToFileURL} from 'node:url';
import fs from 'node:fs';
const OWNER_ID=12054121,REPOSITORY='mriekki/project-forge-platform';
const positive=x=>Number.isSafeInteger(x)&&x>0;
const need=(ok,msg)=>{if(!ok)throw Error(msg);};
const marker='PROJECT_FORGE_NATIVE_SUCCESSOR_AUTHORIZATION_CONSUMED';
export function validateUnusedAuthorization({selection,issue,comments,requestIssue,runAttempt}){
 need(runAttempt===1,'Publish requests cannot be rerun');
 const a=selection.authorization,s=selection.source,p=selection.preview;
 need(positive(a?.issueNumber)&&positive(a.issueId)&&requestIssue!==a.issueNumber&&
 issue?.number===a.issueNumber&&issue.id===a.issueId&&issue.user?.id===OWNER_ID&&
 issue.state==='open'&&issue.title==='[project-forge-native-successor-authorize] '+s.version,
 'Exact open owner-reviewed one-use authorization required');
 const expected={version:s.version,sourceCommit:s.sourceCommit,candidateSha256:s.candidateSha256,
  manifestSha256:s.manifestSha256,previewRunId:p.runId,previewRunAttempt:p.runAttempt};
 need(equal(strictJson(issue.body,8192),expected),'Authorization differs from reviewed release selection');
 need(Array.isArray(comments)&&comments.length===issue.comments&&comments.length<100&&
 comments.every(c=>typeof c.body==='string'&&!c.body.includes(marker)),'Authorization consumed or comment inventory uncertain');
 return true;
}
export function claimAuthorization({selection,request,requestIssue,runAttempt,api}){
 need(request.mode==='publish'&&positive(requestIssue)&&positive(request.publicationRunId)&&runAttempt===1,
  'Exact first publish request required');
 const endpoint='/repos/'+REPOSITORY+'/issues/'+selection.authorization.issueNumber;
 const issue=api('GET',endpoint),comments=api('GET',endpoint+'/comments?per_page=100');
 validateUnusedAuthorization({selection,issue,comments,requestIssue,runAttempt});
 const body=marker+'\n'+JSON.stringify({version:request.version,platformCommit:request.platformCommit,
  selectionSha256:request.selectionSha256,requestIssue,workflowRunId:request.publicationRunId,runAttempt});
 const created=api('POST',endpoint+'/comments',{body});
 need(positive(created?.id)&&created.body===body&&created.user?.login==='github-actions[bot]',
  'Durable authorization consumption not confirmed');
 const closed=api('PATCH',endpoint,{state:'closed',state_reason:'completed'});
 need(closed?.id===issue.id&&closed.state==='closed','Authorization closure not confirmed');
 const observed=api('GET',endpoint+'/comments?per_page=100');
 need(Array.isArray(observed)&&observed.length===comments.length+1&&
  observed.filter(c=>c.body.includes(marker)).length===1&&observed.some(c=>c.id===created.id&&c.body===body),
 'Durable consumption could not be independently reread');
 return {consumed:true,authorizationIssue:issue.number,requestIssue,workflowRunId:request.publicationRunId,runAttempt};
}
function api(method,endpoint,body){
 const args=['api','--method',method,endpoint,...(body?['--input','-']:[])];
 return strictJson(execFileSync('gh',args,{encoding:'utf8',timeout:30000,maxBuffer:1024*1024,
  input:body?JSON.stringify(body):undefined,stdio:['pipe','pipe','pipe']}),1024*1024);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const r=strictJson(fs.readFileSync(process.env.RUNNER_TEMP+'/pf-successor-publish-request.json','utf8'));
  const event=strictJson(fs.readFileSync(process.env.GITHUB_EVENT_PATH,'utf8'));
  console.log(JSON.stringify(claimAuthorization({selection:r.selection,request:r,requestIssue:event.issue.number,
    runAttempt:Number(process.env.GITHUB_RUN_ATTEMPT),api})));
  console.log('PASS durable single-use authorization consumed before preflight');
 }catch(e){console.error('Single-use authorization refused');process.exitCode=2;}
}
