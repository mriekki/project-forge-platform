import test from 'node:test';
import assert from 'node:assert/strict';
import {claimAuthorization,validateUnusedAuthorization} from '../scripts/native-successor-authorization.mjs';
function fixture(){
 const s={version:'4.36.1',sourceCommit:'a'.repeat(40),candidateSha256:'b'.repeat(64),manifestSha256:'c'.repeat(64)};
 const selection={source:s,preview:{runId:5,runAttempt:1},authorization:{issueNumber:7,issueId:70}};
 const issue={number:7,id:70,user:{id:12054121},state:'open',title:'[project-forge-native-successor-authorize] 4.36.1',
 comments:0,body:JSON.stringify({...s,previewRunId:5,previewRunAttempt:1})};
 const request={mode:'publish',version:s.version,platformCommit:'d'.repeat(40),selectionSha256:'e'.repeat(64),publicationRunId:9};
 const comments=[],calls=[];
 const api=(method,path,body)=>{
  calls.push(method);
  if(method==='GET')return path.includes('/comments')?structuredClone(comments):structuredClone(issue);
  if(method==='POST'){const row={id:99,user:{login:'github-actions[bot]'},body:body.body};comments.push(row);issue.comments++;return row;}
  if(method==='PATCH'){issue.state='closed';return structuredClone(issue);}
 };
 return {selection,issue,comments,request,requestIssue:8,runAttempt:1,api,calls};
}
test('one-use claim is recorded, closed and independently reread before preflight',()=>{
 const x=fixture();assert.equal(claimAuthorization(x).consumed,true);
 assert.deepEqual(x.calls,['GET','GET','POST','PATCH','GET']);
 assert.throws(()=>claimAuthorization({...x,requestIssue:10}));
 x.issue.state='open';assert.throws(()=>claimAuthorization(x));
});
test('refuse wrong approval, rerun, incomplete inventory or prior claim',()=>{
 for(const mutate of [x=>x.runAttempt=2,x=>x.issue.user.id=99,x=>x.issue.id=71,
 x=>x.issue.state='closed',x=>x.issue.comments=1,x=>x.issue.body=x.issue.body.replace('4.36.1','4.36.2'),
 x=>{x.comments.push({body:'PROJECT_FORGE_NATIVE_SUCCESSOR_AUTHORIZATION_CONSUMED'});x.issue.comments=1;}]){
  const x=fixture();mutate(x);assert.throws(()=>validateUnusedAuthorization(x));
 }
});
test('ambiguous consumption fails closed; durable claim prevents retries',()=>{
 const x=fixture(),real=x.api;
 x.api=(method,path,body)=>{const result=real(method,path,body);if(method==='POST')throw Error('connection lost');return result;};
 assert.throws(()=>claimAuthorization(x));assert.equal(x.comments.length,1);
 x.api=real;assert.throws(()=>claimAuthorization(x));
});
