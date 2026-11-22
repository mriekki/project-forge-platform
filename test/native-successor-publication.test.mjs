import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolveSuccessorPublication,requireRegistryState,verifyAdmissionWitness,decodeAdmissionWitnessPayload} from '../scripts/native-successor-publication.mjs';
const sha='a'.repeat(40),digest='b'.repeat(64),version='4.36.1';
function fixture(){
 const selection={schemaVersion:1,kind:'project-forge-reviewed-native-successor-selection',
 source:{sourceCommit:sha,workflowRunId:12,runAttempt:1,previousVersion:'4.36.0',previousReceiptSha256:digest,version,manifestSha256:digest,candidateSha256:digest},
 preview:{platformCommit:sha,workflowId:13,runId:14,runAttempt:1},authorization:{issueNumber:44,issueId:55}};
 const selectionBytes=Buffer.from(JSON.stringify(selection));
 const event={action:'opened',sender:{login:'owner'},issue:{state:'open',user:{login:'owner'},title:'[project-forge-native-successor-publish] '+version,
 body:JSON.stringify({version,platformCommit:sha,selectionSha256:createHash('sha256').update(selectionBytes).digest('hex')})}};
 return {selection,selectionBytes,event,owner:'owner',platformSha:sha,currentRunId:15,currentRunAttempt:1};
}
test('successor owner issue binds exact reviewed selection and separates verify mode',()=>{
 const x=fixture();assert.equal(resolveSuccessorPublication(x).mode,'publish');
 const body=JSON.parse(x.event.issue.body);
 x.event.issue.title='[project-forge-native-successor-publish-verify] '+version;
 x.event.issue.body=JSON.stringify({...body,publicationRunId:16,publicationRunAttempt:1,provenanceUrl:'https://search.sigstore.dev/?logIndex=17'});
 assert.equal(resolveSuccessorPublication(x).mode,'verify');
 for(const mutate of [x=>x.event.sender.login='other',x=>x.currentRunAttempt=2,x=>x.platformSha='f'.repeat(40),x=>x.event.issue.body=JSON.stringify({...body,extra:1}),
 x=>x.event.issue.body=x.event.issue.body.slice(0,-1)+',"version":"4.36.1"}',x=>x.selectionBytes=Buffer.from('{}')]){
  const y=fixture();mutate(y);assert.throws(()=>resolveSuccessorPublication(y));
 }
});
test('only exact 404 and predecessor latest allows publication, existing version only recovery',()=>{
 requireRegistryState({mode:'publish',targetStatus:404,latest:'4.36.0',previousVersion:'4.36.0',version});
 requireRegistryState({mode:'verify',targetStatus:200,latest:version,previousVersion:'4.36.0',version});
 for(const status of [200,403,429,500])assert.throws(()=>requireRegistryState({mode:'publish',targetStatus:status,latest:'4.36.0',previousVersion:'4.36.0',version}));
 assert.throws(()=>requireRegistryState({mode:'verify',targetStatus:404,latest:version,previousVersion:'4.36.0',version}));
});
test('successor publisher privilege and shell boundaries',()=>{
 const workflow=fs.readFileSync(new URL('../.github/workflows/npm-publish.yml',import.meta.url),'utf8');
 const pre=workflow.slice(workflow.indexOf('\n  native-successor-preflight:'),workflow.indexOf('\n  native-successor-publish:'));
 const publish=workflow.slice(workflow.indexOf('\n  native-successor-publish:'),workflow.indexOf('\n  native-successor-verify:'));
 const verify=workflow.slice(workflow.indexOf('\n  native-successor-verify:'),workflow.indexOf('\n  native-publish:'));
 assert.match(pre,/PF_NATIVE_SUCCESSOR_PUBLISH_ENABLED == 'true'/);
 assert.match(pre,/git diff --exit-code/);assert.match(pre,/verify-native-publication-provenance\.mjs/);
 assert.doesNotMatch(pre,/id-token: write/);
 assert.match(publish,/id-token: write/);assert.match(publish,/outputs.mode == 'publish'/);assert.match(publish,/github.run_attempt == 1/);
 assert.equal((workflow.match(/id-token: write/g)||[]).length,1);
 assert.match(publish,/sha512-Zov8KhamNneiLdEL/);
 assert.match(publish,/unset NODE_AUTH_TOKEN NPM_TOKEN NPM_CONFIG_USERCONFIG npm_config_userconfig NPM_CONFIG_GLOBALCONFIG npm_config_globalconfig/);
 assert.doesNotMatch(publish,/export npm_config_userconfig=\/dev\/null/);
 assert.match(publish,/user_config="\$RUNNER_TEMP\/pf-successor-publish-user\.npmrc"/);
 assert.match(publish,/global_config="\$RUNNER_TEMP\/pf-successor-publish-global\.npmrc"/);
 assert.match(publish,/export npm_config_userconfig="\$user_config" npm_config_globalconfig="\$global_config"/);
 assert.match(publish,/node "\$RUNNER_TEMP\/pf-publisher\/package\/bin\/npm-cli\.js" --version/);
 assert.match(pre,/needs: native-successor-claim/);
 assert.doesNotMatch(publish,/secrets\.|npm run|npm ci/);
 assert.match(publish,/publish "\$archive" --access public --provenance --ignore-scripts/);
 assert.match(verify,/outputs.mode == 'verify'/);
 assert.doesNotMatch(verify,/id-token: write|secrets\.|npm publish /);
 assert.match(verify,/native-successor-publication\.mjs finalize/);
 if(process.platform!=='win32')for(const match of (pre+publish+verify).matchAll(/^        run: \|\n((?:^          .*\n|^\n)+)/gm)){
  execFileSync('bash',['-n'],{input:match[1].split('\n').map(s=>s.startsWith('          ')?s.slice(10):s).join('\n')});
 }
});


test('admission witness survives GitHub masking without weakening exact identity checks',()=>{
 const source={
   schemaVersion:1,kind:'project-forge-successor-admission-witness',
   selection:{sourceCommit:'a'.repeat(40),version:'4.36.1',
     candidateSha256:'b'.repeat(64)},releaseAuthorized:false,published:false
 };
 const text=JSON.stringify(source),encoded=Buffer.from(text,'utf8').toString('base64url');
 assert.doesNotMatch(encoded,/[{}]/);
 assert.deepEqual(decodeAdmissionWitnessPayload(encoded),source);
 for(const invalid of [
   text,'***"schemaVersion":1***','',encoded+'=',encoded+'*',encoded+'\\n',
   'A', 'A'.repeat(24001),Buffer.from([0xff,0xfe]).toString('base64url'),
   Buffer.from('{"duplicate":1,"duplicate":2}').toString('base64url')
 ])assert.throws(()=>decodeAdmissionWitnessPayload(invalid));
});

test('all successor publisher preflight, publish and recovery repacks use distinct empty npm configs',()=>{
 const workflow=fs.readFileSync(new URL('../.github/workflows/npm-publish.yml',import.meta.url),'utf8');
 const pre=workflow.slice(workflow.indexOf('\n  native-successor-preflight:'),workflow.indexOf('\n  native-successor-publish:'));
 const publish=workflow.slice(workflow.indexOf('\n  native-successor-publish:'),workflow.indexOf('\n  native-successor-verify:'));
 const verify=workflow.slice(workflow.indexOf('\n  native-successor-verify:'),workflow.indexOf('\n  native-publish:'));
 for(const [name,job] of [['preflight',pre],['publish',publish],['verify',verify]]){
   assert.ok(job.length>0,name+' workflow job present');
   assert.match(job,/umask 077/);
   assert.match(job,/user_config="\$RUNNER_TEMP\/pf-native-user\.npmrc"/);
   assert.match(job,/global_config="\$RUNNER_TEMP\/pf-native-global\.npmrc"/);
   assert.match(job,/: > "\$user_config"/);
   assert.match(job,/: > "\$global_config"/);
   assert.match(job,/npm pack --ignore-scripts --offline --userconfig "\$user_config" --globalconfig "\$global_config" --json --pack-destination "\$RUNNER_TEMP"/);
   assert.doesNotMatch(job,/npm pack[^\n]*--userconfig \/dev\/null --globalconfig \/dev\/null/);
 }
 assert.equal((workflow.match(/pf-native-user\.npmrc/g)||[]).length,3);
 assert.equal((workflow.match(/pf-native-global\.npmrc/g)||[]).length,3);
});

test('successor one-use npm 11 dispatch is regression-tested without publication or credentials',()=>{
 const workflow=fs.readFileSync(new URL('../.github/workflows/npm-publish.yml',import.meta.url),'utf8');
 const publish=workflow.slice(workflow.indexOf('\n  native-successor-publish:'),workflow.indexOf('\n  native-successor-verify:'));
 const after=publish.slice(publish.indexOf('Publish exact successor archive through existing trusted publisher'));
 assert.match(after,/umask 077/);
 assert.match(after,/: > "\$user_config"/);
 assert.match(after,/: > "\$global_config"/);
 assert.match(after,/test "\$user_config" != "\$global_config"/);
 assert.match(after,/npm_config_userconfig="\$user_config" npm_config_globalconfig="\$global_config"/);
 assert.doesNotMatch(after,/npm_config_(?:userconfig|globalconfig)=\/dev\/null/);
 assert.match(after,/publish "\$archive" --access public --provenance --ignore-scripts --registry=https:\/\/registry\.npmjs\.org\//);
 const ci=fs.readFileSync(new URL('../.github/workflows/ci.yml',import.meta.url),'utf8');
 assert.match(ci,/matrix\.node == '22'/);
 assert.match(ci,/bash test\/native-successor-pinned-publisher-npm11\.sh/);
 const probe=fs.readFileSync(new URL('./native-successor-pinned-publisher-npm11.sh',import.meta.url),'utf8');
 assert.match(probe,/npm-11\.21\.0\.tgz/);
 assert.match(probe,/sha512-Zov8KhamNneiLdELtj5YALtNmJW4L4fCLTzjfpzXG2w6MSHcf0UxgdlK5uloCuksWT\+7mGUU7wi79cO6RqivPg==/);
 assert.match(probe,/double-loading config/);
 assert.match(probe,/node "\$cli" config list --json/);
 assert.doesNotMatch(probe,/node "\$cli" publish |npm publish |id-token: write/);
});

test('regression: successor preflight import does not execute legacy 4.36.0 CLI',()=>{
 const root=fileURLToPath(new URL('../',import.meta.url));
 for (const mode of ['prepare','finalize','check-recovery','check-absence']) {
  const source=`process.argv[2]=${JSON.stringify(mode)}; await import('./scripts/native-successor-publication.mjs'); console.log('SUCCESSOR_IMPORT_SAFE')`;
  const child=spawnSync(process.execPath,['--input-type=module','--eval',source],{
   cwd:root,encoding:'utf8',timeout:15000,env:{...process.env,RUNNER_TEMP:'/nonexistent-pf-import-test'}});
  assert.equal(child.status,0,`successor import with ${mode} unexpectedly executed old entrypoint: ${child.stderr}`);
  assert.match(child.stdout,/SUCCESSOR_IMPORT_SAFE/);
  assert.doesNotMatch(child.stderr,/pf-source-release-run\\.json|ENOENT/);
 }
});

test('historical publisher remains directly invokable but cannot run from import',()=>{
 const root=fileURLToPath(new URL('../',import.meta.url));
 const imported=spawnSync(process.execPath,['--input-type=module','--eval',
  "process.argv[2]='prepare'; await import('./scripts/first-native-publication.mjs'); console.log('LEGACY_IMPORT_SAFE')"],{
  cwd:root,encoding:'utf8',timeout:15000,env:{...process.env,RUNNER_TEMP:'/nonexistent-pf-import-test'}});
 assert.equal(imported.status,0,imported.stderr);
 assert.match(imported.stdout,/LEGACY_IMPORT_SAFE/);
 const direct=spawnSync(process.execPath,['scripts/first-native-publication.mjs','prepare'],{
  cwd:root,encoding:'utf8',timeout:15000,env:{...process.env,RUNNER_TEMP:'/nonexistent-pf-import-test'}});
 assert.notEqual(direct.status,0,'historical direct entrypoint was unintentionally disabled');
 assert.match(direct.stderr,/ENOENT|ERR_INVALID_ARG_TYPE/);
});
