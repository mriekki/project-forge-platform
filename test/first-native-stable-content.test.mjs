import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('../scripts/verify-first-native-stable-content.py', import.meta.url));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function fixture(change = () => {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'pf-first-stable-'));
  const docs = version => ({
    'package.json': JSON.stringify({name:'@mriekki/project-forge',version,
      publishConfig:{access:'public',provenance:true}}),
    'assets/components.json':JSON.stringify({schemaVersion:2,package:'@mriekki/project-forge',version,
      components:{core:{revision:'a'.repeat(40)}}}),
    'assets/generated/ASSEMBLY.json':JSON.stringify({schemaVersion:2,package:'@mriekki/project-forge',version,
      components:{core:{revision:'a'.repeat(40)}}}),
    'bin/project-forge.mjs':'#!/usr/bin/env node\nconsole.log("fixture");\n'
  });
  function build(label, files) {
    const dir=path.join(root,label);
    const archive=path.join(root,label+'.tgz');
    fs.mkdirSync(dir);
    for(const [name, value] of Object.entries(files)) {
      const target=path.join(dir,'package',name);
      fs.mkdirSync(path.dirname(target),{recursive:true});
      fs.writeFileSync(target,value,{mode:name.startsWith('bin/')?0o755:0o644});
    }
    execFileSync('tar',['-czf',archive,'-C',dir,'package']);
    return archive;
  }
  try {
    const prior=build('prior',docs('4.35.0'));
    const next=docs('4.36.0');
    change(next);
    const candidate=build('candidate',next);
    const run = (digest=hash(fs.readFileSync(prior))) =>
      spawnSync('python3',[script,'--prior',prior,'--candidate',candidate,'--prior-sha256',digest],{encoding:'utf8'});
    return {run,hash:hash(fs.readFileSync(candidate)),cleanup:()=>fs.rmSync(root,{recursive:true,force:true})};
  } catch(err) { fs.rmSync(root,{recursive:true,force:true}); throw err; }
}
test('first stable migration accepts only the exact prior package plus three version updates',()=>{
  const input=fixture();
  try {
    const result=input.run();
    assert.equal(result.status,0,result.stderr);
    const proof=JSON.parse(result.stdout);
    assert.equal(proof.result,'FIRST_NATIVE_STABLE_CONTENT_MATCH');
    assert.equal(proof.candidateSha256,input.hash);
    assert.equal(proof.fileCount,4);
    for (const key of ['releaseAuthorized','published','sourceOwnershipTransferred','productionAuthorized'])
      assert.equal(proof[key],false);
    assert.equal(input.run('0'.repeat(64)).status,2);
  } finally {input.cleanup();}
});
test('first stable migration refuses payload changes, extra or absent files and metadata drift',()=>{
  for (const mutate of [
    x=>x['bin/project-forge.mjs']+='changed',
    x=>delete x['bin/project-forge.mjs'],
    x=>x['extra.txt']='unexpected',
    x=>x['package.json']=JSON.stringify({...JSON.parse(x['package.json']),private:true}),
    x=>x['package.json']=JSON.stringify({...JSON.parse(x['package.json']),version:'4.36.0-preview.7'}),
    x=>x['assets/components.json']=x['assets/components.json'].replace('a'.repeat(40),'b'.repeat(40)),
    x=>x['assets/generated/ASSEMBLY.json']=x['assets/generated/ASSEMBLY.json'].replace('"schemaVersion":2','"schemaVersion":2,"schemaVersion":2')
  ]) {
    const input=fixture(mutate);
    try {const result=input.run();assert.equal(result.status,2,result.stdout);assert.equal(result.stdout,'');}
    finally {input.cleanup();}
  }
});
