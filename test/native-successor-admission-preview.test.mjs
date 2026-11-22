import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolveSuccessorPreview} from '../scripts/native-successor-admission-preview.mjs';
const r={sourceCommit:'a'.repeat(40),workflowRunId:123,runAttempt:1,previousVersion:'4.36.0',
  previousReceiptSha256:'b'.repeat(64),version:'4.36.1',manifestSha256:'c'.repeat(64),candidateSha256:'d'.repeat(64)};
function event(){return {action:'opened',sender:{login:'owner'},issue:{
  state:'open',title:'[project-forge-native-successor-preview]',user:{login:'owner'},body:JSON.stringify(r)}};}
test('exact successor preview request does not authorize publication',()=>{
  assert.deepEqual(resolveSuccessorPreview(event(),'owner'),r);
  for(const mutate of [
    x=>x.sender.login='other',x=>x.issue.state='closed',x=>x.action='edited',
    x=>x.issue.title='[project-forge-native-publish]',
    ...[{sourceCommit:'main'},{runAttempt:0},{workflowRunId:'123'},{version:'4.36.0'},
      {previousVersion:'4.35.0'},{version:'4.36.1-preview.7'},{version:'4.36.1\nBAD=1'},
      {candidateSha256:'wrong'},{publicationAuthorized:true}].map(change=>x=>x.issue.body=JSON.stringify({...r,...change}))
  ]){const x=event();mutate(x);assert.throws(()=>resolveSuccessorPreview(x,'owner'));}
});
test('protected preview defaults off, uses no publisher permission and isolates private output',()=>{
  const body=fs.readFileSync(new URL('../.github/workflows/native-successor-admission-preview.yml',import.meta.url),'utf8');
  for(const value of [
    "vars.PF_NATIVE_SUCCESSOR_PREVIEW_ENABLED == 'true'",
    "vars.PF_MONOREPO_SOURCE_PREVIEW_ENABLED == 'true'",'permissions:\n  contents: read',
    'persist-credentials: false','verify-checkout .private-source','PF_NATIVE_SUCCESSOR_WORKFLOW_ID',
    'npm audit signatures','git merge-base --is-ancestor','test "$status" = 404',
    'pf-successor-private-build.log','pf-successor-reviewed-code','python3 -I -B',
    'verify-assets "$RUNNER_TEMP/pf-successor-stage"','npm pack --ignore-scripts --offline','Recheck authenticated private and public main after preview',
    'RELEASE_AUTHORIZED=false NPM_PUBLISHED=false PRODUCTION_CHANGED=false'
  ])assert.ok(body.includes(value),value);
  for(const value of ['id-token: write','contents: write','issues: write','npm publish ',
    'PROJECT_FORGE_SOURCE_TOKEN','upload-artifact','\n  push:','\n  pull_request:'])
    assert.ok(!body.includes(value),value);
  const rebuild=body.slice(body.indexOf('      - name: Independently derive selection'),body.indexOf('      - name: Recheck authenticated private'));
  assert.doesNotMatch(rebuild,/npm run verify:assets|python3 \.private-source\/|if ! \(/);
  if(process.platform!=='win32')for(const match of body.matchAll(/^        run: \|\n((?:^          .*\n|^\n)+)/gm)){
    execFileSync('bash',['-n'],{input:match[1].split('\n').map(l=>l.startsWith('          ')?l.slice(10):l).join('\n')});
  }
});
