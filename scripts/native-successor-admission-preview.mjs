/** Protected read-only successor preview integration; not a publisher. */
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {pathToFileURL} from 'node:url';
import {verifySuccessorRunEvidence,extractSuccessorProof,REQUIRED_CODE_PATHS} from './native-successor-run-evidence.mjs';
import {verifyPriorRegistryArchive,readReleaseArchiveProjection} from './prior-registry-archive.mjs';
import {compareSuccessorEvidence} from './verify-native-successor-evidence.mjs';
import {validateNativeReceipt} from './native-source-receipt.mjs';
import {verifyAssets} from './verify-assets.mjs';
import {loadPackageData} from '../src/package-data.mjs';

const pins=Object.freeze({
  ".github/workflows/native-successor-main-qualification.yml": "0cb137b10fea08bf6d461b659faaa638c54589cf",
  "tools/release/resolve_successor_request.py": "de3ed44e85b848ffd463102843fd5847e34791ce",
  "tools/release/verify_main_identity.py": "a7919cce83e31c11b506594481837dad5c86c10e",
  "tools/shared/verify_current_main_snapshot.py": "48158c418c4dacdd39206a5d8a068995d76f954b",
  "tools/npm/qualify_native_successor.py": "68a3a84dd57982b95fc6af4fb54064698491ec87",
  "tools/npm/select_native_stable.py": "0bf0aeac8b2ca6e828cfd77a75df4b0aabca3b78",
  "tools/npm/assemble_selected_stable.py": "f60247c196271d01f1e33d9437e58a1fa7da4380",
  "tools/npm/build_manifest_preview.py": "d9fccb28a4a6e15a4322579927f26e2021464317",
  "tools/npm/preview_selected_manifest.py": "c34134ce0b22bcc518dfbc6e44fc7fcc66be9a79",
  "tools/npm/build_candidate.py": "e37c13c6f1166c8d9d9b58d468132c3218be5e9e",
  "tools/npm/build_versioned_preview.py": "be0e792bf9aa6bce49e6031cf7cd5740e876c997",
  "tools/release/native_revision_plan.py": "afa230b1a4961768be0d5e22a2ee14c953c290b7",
  "tools/release/plan_component_revisions.py": "3e93f443d4165b201a30c6aa717a9fa6f266ffae",
  "tests/release/generated_consumer_selected_proof.py": "5bde9bdf3a5b11e323aa6190c96cb0e155da0f36"
});
const title='[project-forge-native-successor-preview]';
const sha=/^[0-9a-f]{40}$/;
const digest=/^[0-9a-f]{64}$/;
const version=/^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$/;
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};
const exact=(x,p)=>typeof x==='string'&&p.test(x);
const positive=x=>Number.isSafeInteger(x)&&x>0;
const hash=b=>createHash('sha256').update(b).digest('hex');
const scratch=()=>process.env.RUNNER_TEMP;
const at=n=>path.join(scratch(),n);
const read=n=>fs.readFileSync(at(n));
const json=n=>JSON.parse(read(n));
const save=(n,x)=>fs.writeFileSync(at(n),JSON.stringify(x)+'\n',{flag:'wx',mode:0o600});

export function resolveSuccessorPreview(event,owner){
  need(typeof owner==='string'&&owner.length>0&&event?.action==='opened'&&
    event.issue?.title===title&&event.issue?.state==='open'&&
    event.issue.user?.login===owner&&event.sender?.login===owner,'Owner-opened preview required');
  const raw=event.issue.body;
  need(typeof raw==='string'&&raw.length<=4096,'Bounded preview request required');
  const r=JSON.parse(raw);
  need(r&&typeof r==='object'&&!Array.isArray(r)&&equal(Object.keys(r).sort(),
    ['sourceCommit','workflowRunId','runAttempt','previousVersion','previousReceiptSha256',
     'version','manifestSha256','candidateSha256'].sort()),'Unexpected preview request fields');
  need(exact(r.sourceCommit,sha)&&positive(r.workflowRunId)&&positive(r.runAttempt)&&
    [r.previousReceiptSha256,r.manifestSha256,r.candidateSha256].every(x=>exact(x,digest))&&
    exact(r.previousVersion,version)&&exact(r.version,version),'Exact reviewed successor selection required');
  const a=r.version.split('.').map(Number),b=r.previousVersion.split('.').map(Number);
  const after=(x,y)=>x.some((v,i)=>v!==y[i]&&x.slice(0,i).every((v,j)=>v===y[j])&&v>y[i]);
  need(after(a,b)&&(equal(b,[4,36,0])||after(b,[4,36,0])),'Expected an advancing native release');
  return r;
}
function gh(endpoint,args=[]){
  // No raw private API error, response, token or locator is emitted publicly.
  return execFileSync('gh',['api',endpoint,...args],{encoding:'utf8',
    timeout:120000,maxBuffer:16*1024*1024,stdio:['ignore','pipe','pipe']});
}
function collect(){
  const r=json('pf-successor-request.json');
  const repository=process.env.SOURCE_REPOSITORY,repositoryId=Number(process.env.SOURCE_ID),
    workflowId=Number(process.env.SOURCE_WORKFLOW_ID);
  need(exact(repository,/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/)&&
    positive(repositoryId)&&positive(workflowId)&&process.env.GH_TOKEN,'Protected reviewed read policy missing');
  // Mask only the protected locator/id; do not expose raw results.
  console.log('::add-mask::'+repository);console.log('::add-mask::'+repositoryId);
  const prefix='/repos/'+repository, query=e=>JSON.parse(gh(prefix+e));
  const repo=query(''),mainRef=query('/git/ref/heads/main'),
    run=query('/actions/runs/'+r.workflowRunId),
    jobs=query('/actions/runs/'+r.workflowRunId+'/attempts/'+r.runAttempt+'/jobs?per_page=100');
  const code=Object.fromEntries(REQUIRED_CODE_PATHS.map(file=>[file,
    JSON.parse(gh(prefix+'/contents/'+file,['--method','GET','-f','ref='+r.sourceCommit,'--jq','{path,type,sha}']))]));
  const result=verifySuccessorRunEvidence({policy:{repository,repositoryId,workflowId,codePins:pins},
    selected:{sourceCommit:r.sourceCommit,workflowRunId:r.workflowRunId,runAttempt:r.runAttempt},
    repo,mainRef,run,jobs,code});
  const proof=extractSuccessorProof(gh(prefix+'/actions/jobs/'+result.sourceJobId+'/logs'));
  save('pf-successor-source-proof.json',proof);
  // Bind the job log to the exact independently observed run and selected source.
  need(proof.sourceCommit===r.sourceCommit&&proof.manifestSha256===r.manifestSha256&&
    proof.candidateSha256===r.candidateSha256&&proof.version===r.version&&
    proof.previousVersion===r.previousVersion&&proof.previousReceiptSha256===r.previousReceiptSha256,
    'Source proof does not match reviewed request');
  fs.appendFileSync(process.env.GITHUB_OUTPUT,'repository='+repository+'\n');
  console.log('Exact source run, reviewed code and final proof compared (read-only).');
}
function localPins(root,head){
  const git=(...args)=>execFileSync('git',['-C',root,...args],
    {encoding:'utf8',timeout:30000,stdio:['ignore','pipe','pipe']}).trim();
  need(git('rev-parse','HEAD')===head&&!git('status','--porcelain','--untracked-files=all'),
    'Exact clean source checkout required');
  const codeRoot=at('pf-successor-reviewed-code');
  fs.mkdirSync(codeRoot,{mode:0o700});
  for(const [file,oid] of Object.entries(pins)){
    need(git('rev-parse','HEAD:'+file)===oid,'Local reviewed source code differs');
    // Import only exact reviewed Python blobs, never adjacent unreviewed
    // modules, checkout-local sitecustomize or candidate shell code.
    if(!file.endsWith('.py'))continue;
    need(/^100(?:644|755) blob [0-9a-f]{40}\t/.test(git('ls-tree','HEAD','--',file)),
      'Reviewed code must be regular Git data');
    const bytes=execFileSync('git',['-C',root,'show','HEAD:'+file],
      {timeout:30000,maxBuffer:2*1024*1024,stdio:['ignore','pipe','pipe']});
    const blob=createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
    need(blob===oid,'Reviewed code blob bytes differ');
    const destination=path.join(codeRoot,file);
    fs.mkdirSync(path.dirname(destination),{recursive:true,mode:0o700});
    fs.writeFileSync(destination,bytes,{flag:'wx',mode:0o600});
  }
}
function verifyStagedAssets(root){
  // Use the independently reviewed PUBLIC verifier, not npm run from the
  // candidate's package shell. Lifecycle scripts are also disabled at pack.
  need(!fs.existsSync(path.join(root,'.npmrc')),'Candidate npm configuration refused');
  verifyAssets(loadPackageData(root));
}
export function verifyPreview({selection,prior,observed,manifestBytes,evidence,sourceProof,archiveBytes}){
  const previous=verifyPriorRegistryArchive({...prior,expectedVersion:selection.previousVersion,
    expectedSha256:selection.previousReceiptSha256}).previous;
  const receipt=validateNativeReceipt(JSON.parse(prior.receiptBytes),selection.previousVersion);
  need(receipt.source.commit===observed.previousSourceCommit&&
    observed.sourceCommit===selection.sourceCommit,'Exact source continuity differs');
  need(Buffer.isBuffer(archiveBytes)&&hash(archiveBytes)===selection.candidateSha256,
    'Separately rebuilt archive differs from reviewed candidate digest');
  const projection=readReleaseArchiveProjection({archiveBytes,expectedVersion:selection.version,
    requirePublishableForm:true});
  const match=compareSuccessorEvidence({manifestBytes,prior:previous,evidence,projection,
    observed:{...observed,targetVersion:selection.version,manifestSha256:selection.manifestSha256}});
  need(equal(sourceProof,{schemaVersion:1,kind:'project-forge-offline-native-successor-proof',
    sourceCommit:selection.sourceCommit,previousVersion:selection.previousVersion,
    previousReceiptSha256:selection.previousReceiptSha256,version:selection.version,
    manifestSha256:selection.manifestSha256,candidateSha256:selection.candidateSha256,
    changedComponents:match.changedComponents,components:evidence.components,reproducibleArchive:true,
    disposableAllComponents:true,disposableGeneratedConsumers:true,previousAcceptanceAuthenticatedHere:false,
    releaseAuthorized:false,published:false,productionAuthorized:false,sourceOwnershipTransferred:false}),
    'Exact private qualification proof differs from independent rebuild');
  return {result:'NATIVE_SUCCESSOR_PREVIEW_MATCH',version:selection.version,
    sourceCommit:selection.sourceCommit,manifestSha256:selection.manifestSha256,
    candidateSha256:selection.candidateSha256,changedComponents:match.changedComponents,
    publicMirrorVerified:false,releaseAuthorized:false,publicationAuthorized:false,
    productionAuthorized:false};
}
function compare(){
  const selection=json('pf-successor-request.json');
  const prior={receiptBytes:read('pf-successor-prior-receipt.json'),
    archiveBytes:read('pf-successor-prior.tgz'),registry:json('pf-successor-prior-registry.json'),
    ...json('pf-successor-prior-observations.json')};
  const preview=verifyPreview({selection,prior,observed:json('pf-successor-observations.json'),
    manifestBytes:read('pf-successor-manifest.json'),evidence:json('pf-successor-assembly.json'),
    sourceProof:json('pf-successor-source-proof.json'),archiveBytes:read('pf-successor-candidate.tgz')});
  // The final public witness is emitted only after the workflow's separately
  // authenticated source and public-main rechecks. It contains no locators,
  // private code, credentials, raw logs, or purported authority.
  save('pf-successor-preview-witness.json',{
    schemaVersion:1,kind:'project-forge-successor-admission-witness',
    selection,platformCommit:process.env.GITHUB_SHA,
    previewRunId:Number(process.env.GITHUB_RUN_ID),previewRunAttempt:Number(process.env.GITHUB_RUN_ATTEMPT),
    priorComponentDigests:prior.componentDigests,
    componentDigests:json('pf-successor-observations.json').componentDigests,
    previousSourceCommit:json('pf-successor-observations.json').previousSourceCommit,
    changedComponents:preview.changedComponents,
    releaseAuthorized:false,published:false,productionAuthorized:false
  });
  console.log(JSON.stringify(preview));
}
function finalizeWitness(){
  const witness=json('pf-successor-preview-witness.json');
  need(exact(witness.platformCommit,sha)&&positive(witness.previewRunId)&&positive(witness.previewRunAttempt),
    'Exact preview run context missing');
  need(witness.platformCommit===process.env.GITHUB_SHA&&witness.previewRunId===Number(process.env.GITHUB_RUN_ID)&&
    witness.previewRunAttempt===Number(process.env.GITHUB_RUN_ATTEMPT),'Preview context differs');
  console.log('PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_BEGIN');
  console.log(JSON.stringify(witness));
  console.log('PROJECT_FORGE_SUCCESSOR_ADMISSION_WITNESS_END');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    switch(process.argv[2]){
      case 'request':{
        const r=resolveSuccessorPreview(JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH,'utf8')),
          process.env.REPOSITORY_OWNER);
        save('pf-successor-request.json',r);
        fs.appendFileSync(process.env.GITHUB_OUTPUT,Object.entries(r).map(([k,v])=>k+'='+v+'\n').join(''));
        break;
      }
      case 'collect':collect();break;
      case 'verify-checkout':localPins(process.argv[3],json('pf-successor-request.json').sourceCommit);break;
      case 'verify-assets':verifyStagedAssets(process.argv[3]);break;
      case 'compare':compare();break;
      case 'witness':finalizeWitness();break;
      default:throw new Error('Unknown read-only preview operation');
    }
  }catch{console.error('Native successor preview refused');process.exitCode=2;}
}
