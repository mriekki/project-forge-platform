/** Exact 4.36.0 cutover: compare independently observed candidate and run data. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {readVerifiedStableCandidate} from './verify-selected-native-stable.mjs';
import {constructNativeIntent,constructNativeReceiptFromIntent,validateNativeIntent} from './native-source-receipt.mjs';
import {verifyNativeStableCandidate} from './native-stable-candidate-verifier.mjs';
import {SOURCE,SOURCE_RUN,VERSION,CANDIDATE_SHA,verifyAdmissionRun,verifyOriginalNativeRun} from './resolve-native-publish.mjs';

const PKG='@mriekki/project-forge';
const ID=1420848802;
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};
const hash=(alg,b,encoding='hex')=>createHash(alg).update(b).digest(encoding);
const read=name=>fs.readFileSync(path.join(process.env.RUNNER_TEMP,name));
const json=name=>JSON.parse(read(name));
const write=(name,value)=>fs.writeFileSync(path.join(process.env.RUNNER_TEMP,name),JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
export function selectPlatformRun(data,expected) {
  const r=data?.workflow_runs?.find(r=>r.head_sha===expected&&r.head_branch==='main'&&
    r.path==='.github/workflows/ci.yml'&&r.event==='push'&&r.status==='completed'&&
    r.conclusion==='success'&&r.repository?.id===ID&&r.head_repository?.id===ID&&
    Number.isSafeInteger(r.id)&&r.id>0&&Number.isSafeInteger(r.run_attempt)&&r.run_attempt>0);
  need(r,'Exact successful current Platform main CI required');
  return {result:'success',workflowRunId:r.id,runAttempt:r.run_attempt};
}
export function verifyRegistryVersion(registry,archive,expected) {
  need(registry?.name===PKG&&registry.version===expected&&
    registry.dist?.shasum===hash('sha1',archive)&&
    registry.dist?.integrity==='sha512-'+hash('sha512',archive,'base64'),
    'Registry identity or exact archive integrity differs');
  return {releaseCandidateSha256:hash('sha256',archive),registryShasum:registry.dist.shasum};
}
export function requireNewVersion({targetStatus,latest}) {
  need(targetStatus===404&&latest==='4.35.0','Cannot establish unused version and exact prior latest');
}
function prepare() {
  const sourceRun=json('pf-source-release-run.json');
  need(sourceRun.id===SOURCE_RUN&&sourceRun.head_sha===SOURCE&&sourceRun.run_attempt===1&&
    sourceRun.event==='issues'&&sourceRun.status==='completed'&&sourceRun.conclusion==='success',
    'Exact qualified source run differs');
  verifyAdmissionRun(json('pf-native-admission-run.json'),json('pf-native-admission-jobs.json'));
  const platformSha=process.env.EXPECTED_COMMIT;
  const platformMain=selectPlatformRun(json('pf-native-platform-ci.json'),platformSha);
  const data=readVerifiedStableCandidate(process.env.RUNNER_TEMP);
  need(hash('sha256',data.archive)===CANDIDATE_SHA,'Exact approved candidate archive digest differs');
  const mirror=read('pf-native-mirror/mriekki-project-forge-4.36.0.tgz');
  need(equal(mirror,data.archive),'Public distribution mirror differs from reconstructed native archive');
  const nativeSourceMain={result:'success',workflowRunId:SOURCE_RUN,runAttempt:1};
  const selected={package:{name:PKG,version:VERSION},platformSource:platformSha,
    source:{mode:'native-monorepo',commit:SOURCE,previousVersion:'4.35.0',
      previousReceiptSha256:data.prior.receiptSha256,manifestSha256:hash('sha256',data.manifestBytes),
      qualificationEvent:'issues'},components:data.prior.components,
    ci:{nativeSourceMain,platformMain},candidateSha256:CANDIDATE_SHA};
  const intent=constructNativeIntent(selected);
  verifyNativeStableCandidate({intent,prior:data.priorInputs,candidateArchiveBytes:data.archive,
    observedSource:{platformSource:platformSha,sourceCommit:SOURCE,manifestSha256:hash('sha256',data.manifestBytes),
      qualificationEvent:'issues',nativeSourceMain,platformMain,componentDigests:data.componentDigests}});
  write('pf-native-intent.json',intent);
  console.log('Exact native candidate, independent source/CI evidence and public mirror match selected release intent.');
}
function finalize() {
  const intent=validateNativeIntent(json('pf-native-intent.json'));
  const archive=read('mriekki-project-forge-4.36.0.tgz');
  const registryArchive=read('pf-native-registry/mriekki-project-forge-4.36.0.tgz');
  need(equal(archive,registryArchive)&&hash('sha256',archive)===intent.candidateSha256,
    'Download differs from exact candidate');
  const artifact=verifyRegistryVersion(json('pf-native-registry/registry.json'),archive,VERSION);
  const time=json('pf-native-npm-time.json')[VERSION];
  need(typeof time==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(time),
    'Exact registry publication time missing');
  const receipt=constructNativeReceiptFromIntent(intent,{artifact,publication:{
    publishedAt:time.replace(/\.\d{3}Z$/,'Z'),workflowRunId:Number(process.env.PUBLICATION_RUN_ID),
    publisher:'github-oidc',registryIdentity:'verified',neutralNpxSmoke:'verified',
    provenance:{signed:true,transparencyLogUrl:process.env.PROVENANCE_URL}}});
  write('publication-evidence.json',receipt);
  console.log('PROJECT_FORGE_NATIVE_PUBLICATION_EVIDENCE_BEGIN');
  console.log(JSON.stringify(receipt));
  console.log('PROJECT_FORGE_NATIVE_PUBLICATION_EVIDENCE_END');
}
// This module also exports read-only helpers imported by the native successor.
// Never execute the historical 4.36.0 CLI when a successor command is importing it.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if(process.argv[2]==='prepare')prepare();
  else if(process.argv[2]==='finalize')finalize();
  else if(process.argv[2]==='check-recovery'){
    verifyOriginalNativeRun(json('pf-native-original-run.json'),json('pf-native-original-jobs.json'),{
      publicationRunId:Number(process.env.PUBLICATION_RUN_ID),sourceCommit:process.env.EXPECTED_COMMIT});
  }
  else if(process.argv[2]==='check-absence')requireNewVersion({
    targetStatus:Number(process.env.TARGET_HTTP_STATUS),latest:json('pf-native-registry-latest.json').version});
}
