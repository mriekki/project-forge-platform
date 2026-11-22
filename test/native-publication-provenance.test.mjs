import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {expectedProvenance,verifyPublicationRun,verifySinglePackageLock} from '../scripts/verify-native-publication-provenance.mjs';
import {strictJson} from '../scripts/strict-json.mjs';
const repo='https://github.com/mriekki/project-forge-platform',pkg='@mriekki/project-forge',version='4.36.0';
const hash=(a,b,e='hex')=>createHash(a).update(b).digest(e);
function fixture(){
 const receipt=JSON.parse(fs.readFileSync(new URL('../release/receipts/4.36.0.json',import.meta.url)));
 const archive=Buffer.from('disposable fixture');
 receipt.artifact={releaseCandidateSha256:hash('sha256',archive),registryShasum:hash('sha1',archive)};
 const registry={name:pkg,version,dist:{shasum:hash('sha1',archive),integrity:'sha512-'+hash('sha512',archive,'base64'),
  tarball:'https://registry.npmjs.org/example.tgz'}};
 const statement={_type:'https://in-toto.io/Statement/v1',predicateType:'https://slsa.dev/provenance/v1',
 subject:[{name:'pkg:npm/%40mriekki/project-forge@4.36.0',digest:{sha512:hash('sha512',archive)}}],
 predicate:{buildDefinition:{buildType:'https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1',
 externalParameters:{workflow:{ref:'refs/heads/main',repository:repo,path:'.github/workflows/npm-publish.yml'}},
 internalParameters:{github:{event_name:'issues',repository_id:'1420848802',repository_owner_id:'12054121'}},
 resolvedDependencies:[{uri:'git+'+repo+'@refs/heads/main',digest:{gitCommit:receipt.platformSource}}]},
 runDetails:{builder:{id:'https://github.com/actions/runner/github-hosted'},
 metadata:{invocationId:repo+'/actions/runs/'+receipt.publication.workflowRunId+'/attempts/1'}}}};
 const bundle={verificationMaterial:{certificate:{rawBytes:'synthetic'},tlogEntries:[{logIndex:receipt.publication.provenance.transparencyLogUrl.split('=')[1]}]},
 dsseEnvelope:{payloadType:'application/vnd.in-toto+json',payload:'',signatures:[{sig:'synthetic'}]}};
 const attestations={attestations:[{predicateType:statement.predicateType,bundle}]};
 const times={[version]:receipt.publication.publishedAt};
 return {receipt,archive,registry,statement,bundle,attestations,times};
}
function selected(x){x.bundle.dsseEnvelope.payload=Buffer.from(JSON.stringify(x.statement)).toString('base64');return expectedProvenance(x);}
test('strict JSON refuses duplicate decoded property names and nested duplicates',()=>{
 assert.deepEqual(strictJson('{"a":[1,{"b":true}]}'),{a:[1,{b:true}]});
 for(const text of ['{"x":1,"x":2}','{"x":{"a":1,"\\u0061":2}}','{"x":1}{}','{"x":[1,]}'])assert.throws(()=>strictJson(text));
});
test('exact subject, immutable workflow certificate policy and receipt invocation',()=>{
 const x=fixture(),r=selected(x);
 assert.equal(r.options.certificateIssuer,'https://token.actions.githubusercontent.com');
 assert.match(repo+'/.github/workflows/npm-publish.yml@refs/heads/main',new RegExp(r.options.certificateIdentityURI));
 assert.equal(r.options.certificateOIDs['1.3.6.1.4.1.57264.1.13'],String.fromCharCode(12,x.receipt.platformSource.length)+x.receipt.platformSource);
 assert.equal(r.options.certificateOIDs['1.3.6.1.4.1.57264.1.21'],String.fromCharCode(12,r.invocation.length)+r.invocation);
 assert.equal(r.options.ctLogThreshold,1);assert.equal(r.options.tlogThreshold,1);
 for(const mutate of [
  x=>x.statement.subject[0].name='pkg:npm/other@4.36.0',
  x=>x.statement.subject[0].digest.sha512='0'.repeat(128),
  x=>x.statement.predicate.buildDefinition.externalParameters.workflow.path='other.yml',
  x=>x.statement.predicate.buildDefinition.resolvedDependencies[0].digest.gitCommit='0'.repeat(40),
  x=>x.statement.predicate.runDetails.metadata.invocationId=repo+'/actions/runs/999/attempts/1',
  x=>x.bundle.verificationMaterial.tlogEntries[0].logIndex='987',
  x=>x.receipt.publication.workflowRunId=999,
  x=>x.registry.dist.integrity='sha512-wrong',
  x=>x.bundle.dsseEnvelope.signatures[0].keyid='registry',
  x=>x.times[version]='2026-01-01T00:00:00Z',
  x=>x.attestations.attestations.push(x.attestations.attestations[0])
 ]){const y=fixture();mutate(y);assert.throws(()=>selected(y));}
});
test('historical publish run may have failed AFTER actual publish; wrong run/attempt/commit/step/marker refused',()=>{
 const x=fixture(),identity=selected(x),r=x.receipt;
 const run={id:identity.runId,run_attempt:identity.attempt,workflow_id:387153969,head_sha:r.platformSource,
 head_branch:'main',path:'.github/workflows/npm-publish.yml',event:'issues',status:'completed',conclusion:'failure',
 repository:{id:1420848802},head_repository:{id:1420848802},actor:{id:12054121},triggering_actor:{id:12054121}};
 const job={id:55,name:'native-publish',run_id:run.id,run_attempt:run.run_attempt,head_sha:run.head_sha,
 head_branch:'main',status:'completed',steps:[{name:'Publish verified native archive with existing npm trusted publisher',
 status:'completed',conclusion:'success'}]};
 const log='2026-11-22T00:10:06.123Z NATIVE_PUBLISHED_PROVENANCE_URL='+r.publication.provenance.transparencyLogUrl+'\n';
 const input={receipt:r,identity,run,jobs:{total_count:1,jobs:[job]},log};
 assert.equal(verifyPublicationRun(input),55);
 for(const change of [
  y=>y.run.run_attempt=2,y=>y.run.head_sha='9'.repeat(40),y=>y.run.actor.id=99,
  y=>y.jobs.jobs[0].steps[0].conclusion='failure',y=>y.log='forged',y=>y.log+=y.log
 ]){const y=structuredClone(input);change(y);assert.throws(()=>verifyPublicationRun(y));}
});
test('neutral lock must have only exact package and exact registry integrity',()=>{
 const x=fixture();const lock={packages:{'':{dependencies:{[pkg]:version}},['node_modules/'+pkg]:{
 version,integrity:x.registry.dist.integrity,resolved:x.registry.dist.tarball}}};
 verifySinglePackageLock({...x,lock});
 lock.packages['node_modules/other']={version:'1.0.0'};assert.throws(()=>verifySinglePackageLock({...x,lock}));
});
