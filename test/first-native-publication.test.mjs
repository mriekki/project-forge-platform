import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolveNativePublish,verifyAdmissionRun,verifyOriginalNativeRun,CANDIDATE_SHA,VERSION} from '../scripts/resolve-native-publish.mjs';
import {selectPlatformRun,requireNewVersion,verifyRegistryVersion} from '../scripts/first-native-publication.mjs';
import {createHash} from 'node:crypto';
const head='a'.repeat(40);
function request(){
  return {owner:'owner',platformSha:head,currentRunId:100,event:{action:'opened',sender:{login:'owner'},
    issue:{state:'open',user:{login:'owner'},title:'[project-forge-native-publish] 4.36.0',
      body:JSON.stringify({version:VERSION,sourceCommit:head,candidateSha256:CANDIDATE_SHA})}}};
}
test('first native publication requires exact owner, version, archive and Platform commit',()=>{
  assert.equal(resolveNativePublish(request()).mode,'publish');
  for(const change of [
    x=>x.event.sender.login='other',x=>x.event.issue.state='closed',
    x=>x.event.issue.title='[project-forge-publish] 4.36.0',
    x=>x.platformSha='b'.repeat(40),x=>x.event.action='edited',
    x=>x.event.issue.body=JSON.stringify({...JSON.parse(x.event.issue.body),version:'4.37.0'}),
    x=>x.event.issue.body=JSON.stringify({...JSON.parse(x.event.issue.body),candidateSha256:'0'.repeat(64)}),
    x=>x.event.issue.body=JSON.stringify({...JSON.parse(x.event.issue.body),approve:true})
  ]){const x=request();change(x);assert.throws(()=>resolveNativePublish(x));}
});
test('native recovery request cannot invoke publication and binds original run and signed URL',()=>{
  const x=request();x.event.issue.title='[project-forge-native-publish-verify] 4.36.0';
  const body={...JSON.parse(x.event.issue.body),publicationRunId:99,provenanceUrl:'https://search.sigstore.dev/?logIndex=123'};
  x.event.issue.body=JSON.stringify(body);
  assert.equal(resolveNativePublish(x).mode,'verify');
  for(const change of [{publicationRunId:100},{provenanceUrl:'https://untrusted.invalid'},{publicationRunId:0}]){
    x.event.issue.body=JSON.stringify({...body,...change});assert.throws(()=>resolveNativePublish(x));
  }
});
test('recovery-only workflow may advance while receipt preserves exact publishing commit',()=>{
  const x=request();
  x.event.issue.title='[project-forge-native-publish-verify] 4.36.0';
  const body={...JSON.parse(x.event.issue.body),sourceCommit:'b4806c1d2e49fcfda9bd0446d0842ac691d73cd3',
    publicationRunId:44965248785,provenanceUrl:'https://search.sigstore.dev/?logIndex=4034417139'};
  x.event.issue.body=JSON.stringify(body);
  const resolved=resolveNativePublish(x);
  assert.equal(resolved.mode,'verify');
  assert.equal(resolved.sourceCommit,body.sourceCommit);
  assert.equal(resolved.publicationRunId,body.publicationRunId);
  for(const change of [{sourceCommit:'c'.repeat(40)},{publicationRunId:99}]){
    x.event.issue.body=JSON.stringify({...body,...change});assert.throws(()=>resolveNativePublish(x));
  }
});
test('native candidate requires an authenticated exact main run; absence is only HTTP 404 with prior latest',()=>{
  const run={id:1,run_attempt:1,head_sha:head,head_branch:'main',path:'.github/workflows/ci.yml',
    event:'push',status:'completed',conclusion:'success',repository:{id:1420848802},head_repository:{id:1420848802}};
  assert.equal(selectPlatformRun({workflow_runs:[run]},head).workflowRunId,1);
  for(const changed of [{event:'pull_request'},{conclusion:'failure'},{head_sha:'b'.repeat(40)},{run_attempt:0}]){
    assert.throws(()=>selectPlatformRun({workflow_runs:[{...run,...changed}]},head));
  }
  requireNewVersion({targetStatus:404,latest:'4.35.0'});
  for(const status of [0,200,403,429,500])assert.throws(()=>requireNewVersion({targetStatus:status,latest:'4.35.0'}));
  assert.throws(()=>requireNewVersion({targetStatus:404,latest:'4.37.0'}));
});
test('exact native registry bytes bind digest and reject different version or integrity',()=>{
  const bytes=Buffer.from('fixture');
  const h=(a,e='hex')=>createHash(a).update(bytes).digest(e);
  const registry={name:'@mriekki/project-forge',version:VERSION,dist:{shasum:h('sha1'),integrity:'sha512-'+h('sha512','base64')}};
  assert.equal(verifyRegistryVersion(registry,bytes,VERSION).releaseCandidateSha256,h('sha256'));
  assert.throws(()=>verifyRegistryVersion(registry,Buffer.from('wrong'),VERSION));
  assert.throws(()=>verifyRegistryVersion(registry,bytes,'4.37.0'));
});
test('native publisher uses existing workflow identity, exact rebuilt digest and recovery-only behavior',()=>{
  const workflow=fs.readFileSync(new URL('../.github/workflows/npm-publish.yml',import.meta.url),'utf8');
  const body=workflow.slice(workflow.indexOf('\n  native-publish:'));
  assert.match(body,/github\.event\.sender\.login == github\.repository_owner/);
  assert.match(body,/github\.ref == 'refs\/heads\/main'/);
  assert.match(body,/Collect authenticated private source and exact release CI evidence/);
  assert.match(body,/Verify exact selected native release intent and public mirror/);
  assert.match(body,/Reverify native canonical and packaged Deployment recovery safety/);
  assert.match(body,/d098f7ff91e6c051f229961ea0458e9c4519f55b682bb1103ddb2fb27f8d46b4/);
  assert.match(body,/Verify unused target release and exact previous registry latest/);
  assert.match(body,/- name: Publish verified native archive with existing npm trusted publisher\n        id: native_npm\n        if: steps.native_request.outputs.mode == 'publish'/);
  assert.match(body,/npm audit signatures/);
  assert.match(body,/gh api --allow-escape-sequences/);
  assert.match(body,/git merge-base --is-ancestor/);
  assert.match(body,/Unapproved recovery drift/);
  assert.match(body,/Verify exact original native publication run for recovery/);
  assert.match(body,/node scripts\/first-native-publication.mjs finalize/);
  assert.doesNotMatch(body,/secrets\.PROJECT_FORGE_SOURCE_TOKEN|upload-artifact|contents: write/);
  assert.equal([...body.matchAll(/^\s+npm publish /gm)].length,1);
  if(process.platform!=='win32'){
    for(const match of body.matchAll(/^        run: \|\n((?:^          .*\n|^\n)+)/gm)){
      const bash=match[1].split('\n').map(s=>s.startsWith('          ')?s.slice(10):s).join('\n');
      execFileSync('bash',['-n'],{input:bash,encoding:'utf8'});
    }
  }
});
