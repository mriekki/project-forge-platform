/** Exact package-specific npm provenance and original publication evidence.
 * Uses npm's pinned bundled Sigstore verifier and its standard public-good
 * trust roots, never a self-declared certificate or new trust service.
 * No source credential, candidate execution or publishing authority.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {isDeepStrictEqual as equal} from 'node:util';
import {pathToFileURL} from 'node:url';
import {validateNativeReceipt} from './native-source-receipt.mjs';
import {strictJson} from './strict-json.mjs';

const PKG='@mriekki/project-forge';
const REPO='https://github.com/mriekki/project-forge-platform';
const WORKFLOW='.github/workflows/npm-publish.yml';
const SIGNER=REPO+'/'+WORKFLOW+'@refs/heads/main';
const SLSA='https://slsa.dev/provenance/v1';
const ISSUER='https://token.actions.githubusercontent.com';
const REPOSITORY_ID=1420848802,OWNER_ID=12054121,WORKFLOW_ID=387153969;
const OID='1.3.6.1.4.1.57264.1.';
const positive=x=>Number.isSafeInteger(x)&&x>0;
const need=(x,m)=>{if(!x)throw Error(m);};
const hash=(a,b,e='hex')=>createHash(a).update(b).digest(e);
const exact=(v,p)=>typeof v==='string'&&p.test(v);
const sha=/^[0-9a-f]{40}$/;
function fields(x,keys,label){need(x&&typeof x==='object'&&!Array.isArray(x)&&
 equal(Object.keys(x).sort(),[...keys].sort()),'Invalid '+label);}
function envelope(bundle){
 need(bundle&&bundle.dsseEnvelope?.payloadType==='application/vnd.in-toto+json'&&
 typeof bundle.dsseEnvelope.payload==='string'&&bundle.dsseEnvelope.payload.length<=128*1024&&
 Array.isArray(bundle.dsseEnvelope.signatures)&&bundle.dsseEnvelope.signatures.length===1&&
 !bundle.dsseEnvelope.signatures[0].keyid&&
 (bundle.verificationMaterial?.certificate||bundle.verificationMaterial?.x509CertificateChain)&&
 !bundle.verificationMaterial?.publicKey,'Expected a single keyless provenance bundle');
 return strictJson(new TextDecoder('utf8',{fatal:true}).decode(Buffer.from(bundle.dsseEnvelope.payload,'base64')),64*1024);
}
export function expectedProvenance({receipt,registry,archive,attestations,times}){
 validateNativeReceipt(receipt);
 const version=receipt.package.version,source=receipt.platformSource,runId=receipt.publication.workflowRunId;
 need(Buffer.isBuffer(archive)&&archive.length>0&&archive.length<=32*1024*1024&&
 hash('sha256',archive)===receipt.artifact.releaseCandidateSha256&&hash('sha1',archive)===receipt.artifact.registryShasum&&
 registry?.name===PKG&&registry.version===version&&registry.dist?.shasum===hash('sha1',archive)&&
 registry.dist?.integrity==='sha512-'+hash('sha512',archive,'base64'),'Exact registry subject bytes differ');
 const time=times?.[version];
 need(exact(time,/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/)&&
 time.replace(/\.\d{3}Z$/,'Z')===receipt.publication.publishedAt,'Registry publication time differs');
 const rows=attestations?.attestations;
 need(Array.isArray(rows)&&rows.length>=1&&rows.length<=8,'Missing package-specific attestation inventory');
 const provenance=rows.filter(x=>x?.predicateType===SLSA);
 need(provenance.length===1,'Exactly one package-specific SLSA provenance required');
 const bundle=provenance[0].bundle,statement=envelope(bundle);
 fields(statement,['_type','subject','predicateType','predicate'],'signed in-toto statement');
 need(statement._type==='https://in-toto.io/Statement/v1'&&statement.predicateType===SLSA&&
 equal(statement.subject,[{name:'pkg:npm/%40mriekki/project-forge@'+version,digest:{sha512:hash('sha512',archive)}}]),
 'Signed subject name, version or digest differs');
 const definition=statement.predicate?.buildDefinition,detail=statement.predicate?.runDetails;
 need(definition?.buildType==='https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1'&&
 equal(definition.externalParameters?.workflow,{ref:'refs/heads/main',repository:REPO,path:WORKFLOW})&&
 equal(definition.internalParameters?.github,{event_name:'issues',repository_id:String(REPOSITORY_ID),repository_owner_id:String(OWNER_ID)})&&
 equal(definition.resolvedDependencies,[{uri:'git+'+REPO+'@refs/heads/main',digest:{gitCommit:source}}])&&
 detail?.builder?.id==='https://github.com/actions/runner/github-hosted','Signed workflow or source identity differs');
 const prefix=REPO+'/actions/runs/'+runId+'/attempts/';
 const invocation=detail.metadata?.invocationId;
 need(typeof invocation==='string'&&invocation.startsWith(prefix)&&/^[1-9][0-9]{0,5}$/.test(invocation.slice(prefix.length)),
 'Signed invocation does not match receipt publication run');
 const attempt=Number(invocation.slice(prefix.length));
 const logIndex=receipt.publication.provenance.transparencyLogUrl.split('=')[1];
 const entries=bundle.verificationMaterial?.tlogEntries;
 need(Array.isArray(entries)&&entries.length===1&&String(entries[0].logIndex)===logIndex,
 'Transparency log index differs from receipt');
 // Enforce the SAME non-falsifiable certificate OIDs as the signed statement.
 // Sigstore verifies signature, Fulcio chain, SCT and Rekor inclusion, plus
 // all these OID values. A matching unsigned statement is never sufficient.
 const certificateOIDs=Object.fromEntries(Object.entries({
  9:SIGNER,10:source,11:'github-hosted',12:REPO,13:source,14:'refs/heads/main',
  15:String(REPOSITORY_ID),17:String(OWNER_ID),18:SIGNER,19:source,20:'issues',21:invocation,22:'public'
 }).map(([k,v])=>[OID+k,v]));
 const options={certificateIssuer:ISSUER,
 certificateIdentityURI:'^'+SIGNER.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$',
 certificateOIDs,ctLogThreshold:1,tlogThreshold:1,timeout:30000,retry:2};
 return {bundle,options,runId,attempt,logIndex,source,version,invocation};
}
export function verifyPublicationRun({receipt,identity,run,jobs,log}){
 need(run?.id===identity.runId&&run.run_attempt===identity.attempt&&run.workflow_id===WORKFLOW_ID&&
 run.head_sha===receipt.platformSource&&run.head_branch==='main'&&run.path===WORKFLOW&&run.event==='issues'&&
 run.status==='completed'&&run.repository?.id===REPOSITORY_ID&&run.head_repository?.id===REPOSITORY_ID&&
 run.actor?.id===OWNER_ID&&run.triggering_actor?.id===OWNER_ID,'Historical publication run identity differs');
 need(Array.isArray(jobs?.jobs)&&jobs.total_count===jobs.jobs.length,'Incomplete historical publication job inventory');
 const first=receipt.package.version==='4.36.0',name=first?'native-publish':'native-successor-publish';
 const stepName=first?'Publish verified native archive with existing npm trusted publisher':
 'Publish exact successor archive through existing trusted publisher';
 const matches=jobs.jobs.filter(j=>j.name===name);
 need(matches.length===1,'Exact historical trusted-publisher job required');
 const j=matches[0];
 need(positive(j.id)&&j.run_id===run.id&&j.run_attempt===identity.attempt&&j.head_sha===receipt.platformSource&&
 j.head_branch==='main'&&j.status==='completed','Historical publication job differs');
 const step=j.steps?.filter(s=>s.name===stepName);
 need(step?.length===1&&step[0].status==='completed'&&step[0].conclusion==='success','Actual publish step did not succeed');
 const marker=(first?'NATIVE_PUBLISHED_PROVENANCE_URL=':'NATIVE_SUCCESSOR_PUBLISHED_PROVENANCE_URL=')+receipt.publication.provenance.transparencyLogUrl;
 need(typeof log==='string'&&Buffer.byteLength(log)<=16*1024*1024&&
 log.split(/\r?\n/).map(x=>x.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z /,'')).filter(x=>x===marker).length===1,
 'Actual original publish log does not bind signed transparency URL');
 return j.id;
}
export function verifySinglePackageLock({lock,receipt,registry}){
 const root=lock?.packages?.[''],entry=lock?.packages?.['node_modules/'+PKG];
 need(equal(Object.keys(lock?.packages??{}).sort(),['','node_modules/'+PKG])&&
 equal(root?.dependencies,{[PKG]:receipt.package.version})&&entry?.version===receipt.package.version&&
 entry.integrity===registry.dist.integrity&&entry.resolved===registry.dist.tarball,'Neutral registry proof is not limited to exact package');
}
function registryURL(value,version){
 const url=new URL(value);
 need(url.origin==='https://registry.npmjs.org'&&!url.username&&!url.password&&!url.search&&!url.hash&&
 decodeURIComponent(url.pathname)==='/-/npm/v1/attestations/'+PKG+'@'+version,'Unexpected registry attestation URL');
 return url;
}
async function boundedFetch(url){
 const res=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(45000)});
 need(res.ok&&new URL(res.url).href===url.href,'Exact registry attestation fetch failed');
 const parts=[];let length=0;
 for await(const part of res.body){
  length+=part.length;need(length<=2*1024*1024,'Oversized registry attestation response');parts.push(Buffer.from(part));
 }
 return strictJson(Buffer.concat(parts).toString('utf8'),2*1024*1024);
}
function api(endpoint,logs=false){
 return execFileSync('gh',['api',...(logs?['--allow-escape-sequences']:[]),endpoint],{
  timeout:90000,maxBuffer:16*1024*1024,encoding:'utf8',stdio:['ignore','pipe','pipe']});
}
export async function qualifyPriorProvenance({receipt,registry,archive,times,lock,npmRoot}){
 verifySinglePackageLock({lock,receipt,registry});
 const url=registryURL(registry.dist.attestations?.url,receipt.package.version);
 const attestations=await boundedFetch(url);
 const identity=expectedProvenance({receipt,registry,archive,attestations,times});
 const require=createRequire(path.join(npmRoot,'package.json'));
 need(require('./package.json').name==='npm'&&require('./package.json').version==='11.21.0','Pinned npm verifier required');
 const sigstore=require('sigstore');
 await sigstore.verify(identity.bundle,identity.options);
 const prefix='/repos/mriekki/project-forge-platform/actions/runs/'+identity.runId;
 const run=JSON.parse(api(prefix+'/attempts/'+identity.attempt));
 const jobs=JSON.parse(api(prefix+'/attempts/'+identity.attempt+'/jobs?per_page=100'));
 const name=identity.version==='4.36.0'?'native-publish':'native-successor-publish';
 const row=jobs.jobs?.filter(j=>j.name===name);
 need(row?.length===1&&positive(row[0].id),'Exact original publication log missing');
 verifyPublicationRun({receipt,identity,run,jobs,log:api('/repos/mriekki/project-forge-platform/actions/jobs/'+row[0].id+'/logs',true)});
 return {version:identity.version,source:identity.source,runId:identity.runId,runAttempt:identity.attempt,
 logIndex:identity.logIndex,archiveVerified:true,certificateVerified:true,publicationRunVerified:true,
 publicationAuthorized:false,productionAuthorized:false};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const [receipt,registry,archive,times,lock,npmRoot]=process.argv.slice(2);
  const j=f=>strictJson(fs.readFileSync(f,'utf8'),2*1024*1024);
  const result=await qualifyPriorProvenance({receipt:j(receipt),registry:j(registry),archive:fs.readFileSync(archive),times:j(times),lock:j(lock),npmRoot});
  console.log(JSON.stringify(result));
  console.log('PASS: exact predecessor signed certificate, package subject, registry archive, transparency log and actual publication run');
 }catch(e){console.error('Exact predecessor provenance verification refused: '+e.message);process.exitCode=2;}
}
