import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync, spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
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
  const duplicate=event();
  duplicate.issue.body=JSON.stringify(r).slice(0,-1)+',"version":"4.36.1"}';
  assert.throws(()=>resolveSuccessorPreview(duplicate,'owner'));
});
test('protected preview defaults off, uses no publisher permission and isolates private output',()=>{
  const body=fs.readFileSync(new URL('../.github/workflows/native-successor-admission-preview.yml',import.meta.url),'utf8');
  for(const value of [
    "vars.PF_NATIVE_SUCCESSOR_PREVIEW_ENABLED == 'true'",
    "vars.PF_MONOREPO_SOURCE_PREVIEW_ENABLED == 'true'",'permissions:\n  contents: read',
    'persist-credentials: false','verify-checkout "$RUNNER_TEMP/pf-successor-private-source"','PF_NATIVE_SUCCESSOR_WORKFLOW_ID','PF_NATIVE_SUCCESSOR_REVIEWED_HARNESS','verify-native-publication-provenance.mjs','fetch-source',
    'audit signatures','git merge-base --is-ancestor','test "$status" = 404',
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

test('rebuild diagnostics expose only a single allowlisted stage value',()=>{
  const body=fs.readFileSync(new URL('../.github/workflows/native-successor-admission-preview.yml',import.meta.url),'utf8');
  const rebuild=body.slice(body.indexOf('      - name: Independently derive selection'),body.indexOf('      - name: Recheck authenticated private'));
  const trap=rebuild.split('\n').find(line=>line.trim().startsWith("trap '"))?.trim();
  assert.ok(trap,'expected reviewed ERR trap');
  assert.equal((trap.match(/cat "\$RUNNER_TEMP\/pf-successor-rebuild-stage"/g)||[]).length,1,'do not reread mutable diagnostics');
  const scratch=fs.mkdtempSync(join(tmpdir(),'pf-stage-'));
  try {
    for(const [marker,exposed] of [
      ['assemble',true],
      ['pack',true],
      ['select\nPRIVATE_SOURCE_TOKEN=DO_NOT_LOG',false],
      ['$(echo PRIVATE_SOURCE_TOKEN=DO_NOT_LOG)',false]
    ]){
      fs.writeFileSync(join(scratch,'pf-successor-rebuild-stage'),marker);
      const result=spawnSync('bash',['-c',['set -e',trap,'false'].join('\n')],{
        env:{...process.env,RUNNER_TEMP:scratch},encoding:'utf8'});
      assert.equal(result.status,1);
      assert.doesNotMatch(result.stderr,/PRIVATE_SOURCE_TOKEN|DO_NOT_LOG/);
      if(exposed)assert.match(result.stderr,new RegExp('reviewed stage: '+marker));
      else assert.match(result.stderr,/before stage selection/);
    }
  } finally {fs.rmSync(scratch,{recursive:true,force:true});}
});


test('npm pack uses isolated user and global configurations, outside assembled candidate',()=>{
  const body=fs.readFileSync(new URL('../.github/workflows/native-successor-admission-preview.yml',import.meta.url),'utf8');
  const rebuild=body.slice(body.indexOf('      - name: Independently derive selection'),body.indexOf('      - name: Recheck authenticated private'));
  for(const required of ['user_config="$RUNNER_TEMP/pf-successor-pack-user.npmrc"',
    'global_config="$RUNNER_TEMP/pf-successor-pack-global.npmrc"',
    ': > "$user_config"',': > "$global_config"','umask 077',
    '--ignore-scripts --offline --userconfig "$user_config" --globalconfig "$global_config"'])
    assert.ok(rebuild.includes(required),required);
  assert.doesNotMatch(rebuild,/--userconfig \/dev\/null --globalconfig \/dev\/null/);

  const scratch=fs.mkdtempSync(join(tmpdir(),'pf-pack-config-'));
  try{
    const stage=join(scratch,'candidate');
    fs.mkdirSync(stage);
    fs.writeFileSync(join(stage,'package.json'),JSON.stringify({
      name:'@mriekki/project-forge',version:'4.36.1',
      files:['readme.txt'],publishConfig:{access:'public',provenance:true}
    }));
    fs.writeFileSync(join(stage,'readme.txt'),'synthetic package only\\n');
    const userConfig=join(scratch,'user.npmrc'),globalConfig=join(scratch,'global.npmrc');
    fs.writeFileSync(userConfig,'',{mode:0o600});
    fs.writeFileSync(globalConfig,'',{mode:0o600});
    const packed=spawnSync('npm',['pack','--ignore-scripts','--offline',
      '--userconfig',userConfig,'--globalconfig',globalConfig,'--json',
      '--pack-destination',scratch],{cwd:stage,encoding:'utf8'});
    assert.equal(packed.status,0,'isolated empty npm configs must permit offline pack');
    const result=JSON.parse(packed.stdout);
    assert.equal(result[0].filename,'mriekki-project-forge-4.36.1.tgz');
    assert.ok(fs.existsSync(join(scratch,result[0].filename)));
  }finally{fs.rmSync(scratch,{recursive:true,force:true});}
});


test('successor witness is encoded before GitHub log masking and never logged as raw JSON',()=>{
 const script=fs.readFileSync(new URL('../scripts/native-successor-admission-preview.mjs',import.meta.url),'utf8');
 const start=script.indexOf('function finalizeWitness()');
 const end=script.indexOf('if(process.argv[1]',start);
 assert.ok(start>0&&end>start);
 const finalize=script.slice(start,end);
 assert.match(finalize,/PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_BEGIN/);
 assert.match(finalize,/PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_END/);
 assert.match(finalize,/Buffer\.from\(JSON\.stringify\(witness\),'utf8'\)\.toString\('base64url'\)/);
 assert.doesNotMatch(finalize,/console\.log\(JSON\.stringify\(witness\)\)/);
});
