/** Read-only on-demand evidence projection around the existing native verifier.
 * This module does not create a new trust root, sign, publish, or authorize.
 * A consumer must independently bind the artifact to the actual successful
 * owner-repository workflow run and the receipt bytes at its reviewed commit.
 */
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {strictJson} from './strict-json.mjs';
import {validateNativeReceipt} from './native-source-receipt.mjs';
import {qualifyPriorProvenance} from './verify-native-publication-provenance.mjs';

const REPOSITORY='mriekki/project-forge-platform';
const PACKAGE='@mriekki/project-forge';
const VERSION=/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const SHA=/^[0-9a-f]{40}$/;
const LOG=/^[0-9]+$/;
const need=(ok,message)=>{if(!ok)throw Error(message);};
const positive=x=>Number.isSafeInteger(x)&&x>0;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');

export function exactVersion(value){
  need(typeof value==='string'&&value.length<=40&&VERSION.test(value),'Exact stable package version required');
  return value;
}

export function proofContext(env){
  const {GITHUB_REPOSITORY:repository,GITHUB_SHA:commit,GITHUB_REF:ref,
    GITHUB_EVENT_NAME:event,GITHUB_RUN_ID:run,GITHUB_RUN_ATTEMPT:attempt}=env;
  need(repository===REPOSITORY&&typeof commit==='string'&&SHA.test(commit),
    'Exact owner Platform workflow context required');
  need((event==='workflow_dispatch'&&ref==='refs/heads/main')||
    (event==='pull_request'&&typeof ref==='string'&&/^refs\/pull\/[1-9][0-9]*\/merge$/.test(ref)),
    'Unsupported proof execution context');
  need(typeof run==='string'&&/^[1-9][0-9]*$/.test(run)&&positive(Number(run))&&
    typeof attempt==='string'&&/^[1-9][0-9]*$/.test(attempt)&&positive(Number(attempt)),
    'Exact proof run and attempt required');
  return {repository,commit,ref,event,runId:Number(run),runAttempt:Number(attempt)};
}

export function selectVersion({event,requested,descriptor}){
  if(event==='workflow_dispatch')return exactVersion(requested);
  need(event==='pull_request'&&descriptor?.schemaVersion===1&&descriptor.channel==='stable'&&
    descriptor.generation?.package===PACKAGE,'Stable proof selection unavailable');
  return exactVersion(descriptor.generation.packageVersion);
}

function receiptFrom(bytes,version){
  need(Buffer.isBuffer(bytes)&&bytes.length>0&&bytes.length<=1024*1024,'Bounded receipt bytes required');
  return validateNativeReceipt(strictJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes)),version);
}

// This pure projection is NOT a verifier. Only the workflow's actual
// invocation of qualifyPriorProvenance may supply its verification result.
export function projectProof({receiptBytes,version,verified,env,observedAt}){
  exactVersion(version);
  const receipt=receiptFrom(receiptBytes,version), context=proofContext(env);
  need(verified?.version===version&&verified.source===receipt.platformSource&&
    verified.runId===receipt.publication.workflowRunId&&positive(verified.runAttempt)&&
    typeof verified.logIndex==='string'&&LOG.test(verified.logIndex)&&
    'https://search.sigstore.dev/?logIndex='+verified.logIndex===receipt.publication.provenance.transparencyLogUrl&&
    verified.archiveVerified===true&&verified.certificateVerified===true&&verified.publicationRunVerified===true&&
    verified.publicationAuthorized===false&&verified.productionAuthorized===false,
    'Native verifier result differs from the exact receipt');
  need(typeof observedAt==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(observedAt)&&
    !Number.isNaN(Date.parse(observedAt))&&new Date(observedAt).toISOString()===observedAt,
    'Exact proof observation time required');
  return {schemaVersion:1,kind:'project-forge-native-package-provenance-observation',
    package:{name:PACKAGE,version},receiptSha256:hash(receiptBytes),
    archiveSha256:receipt.artifact.releaseCandidateSha256,
    platformSource:receipt.platformSource,publicationRunId:verified.runId,
    publicationRunAttempt:verified.runAttempt,transparencyLogIndex:verified.logIndex,
    observedAt,proofWorkflow:'.github/workflows/native-package-provenance-status.yml',
    proofContext:context,archiveVerified:true,certificateVerified:true,
    publicationRunVerified:true,publicationAuthorized:false,productionAuthorized:false,
    authorizesMutation:false};
}

async function main(){
  const [operation,...args]=process.argv.slice(2);
  const json=file=>strictJson(fs.readFileSync(file,'utf8'),2*1024*1024);
  if(operation==='select'){
    need(args.length===0,'Unexpected proof selection arguments');
    const context=proofContext(process.env);
    const version=selectVersion({event:context.event,requested:process.env.REQUESTED_VERSION,
      descriptor:context.event==='pull_request'?json('chatgpt/current.json'):undefined});
    receiptFrom(fs.readFileSync('release/receipts/'+version+'.json'),version);
    fs.appendFileSync(process.env.GITHUB_ENV,'PROOF_VERSION='+version+'\n');
    return;
  }
  need(operation==='verify'&&args.length===6,'Expected registry, archive, times, lock, pinned npm root and proof output');
  proofContext(process.env);
  const version=exactVersion(process.env.PROOF_VERSION);
  const [registry,archive,times,lock,npmRoot,output]=args;
  const receiptBytes=fs.readFileSync('release/receipts/'+version+'.json');
  const receipt=receiptFrom(receiptBytes,version);
  const verified=await qualifyPriorProvenance({receipt,registry:json(registry),
    archive:fs.readFileSync(archive),times:json(times),lock:json(lock),npmRoot});
  const proof=projectProof({receiptBytes,version,verified,env:process.env,observedAt:new Date().toISOString()});
  fs.writeFileSync(output,JSON.stringify(proof,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log('PASS: exact already-published native package provenance observed; no release or deployment authorized');
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{await main();}
  catch{console.error('Native package proof unavailable or inconsistent; inspect authorized evidence and retry. No publication attempted.');process.exitCode=2;}
}
