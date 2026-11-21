/** Read-only first stable candidate admission. Not a release intent or publisher. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';
import {pathToFileURL} from 'node:url';
import {verifyHistoricalRun} from './verify-selected-native-preview.mjs';
import {verifyPriorRegistryArchive,readReleaseArchiveProjection} from './prior-registry-archive.mjs';

const SOURCE = '14415666dd8b698f540f8f68f82971ea17884374';
const MANIFEST = 'af2a6dcb3c34d782828de3f28a149ad32379dd52c46585a9a8308bddcd32bf31';
const RECEIPT = '9541dd1b7db4208e8407f6148515aa9f9c39dc38fbaa018bd24bd48d04a58009';
const PREVIOUS_SOURCE = 'a5ebca39bae777aaf81ad29fb50d92cdcfa0c272';
const ids = ['authentication','core','deployment','feedback','release-notes'];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const need = (ok,msg) => {if(!ok) throw new Error(msg);};

export function compareStableEvidence({evidence,selected,prior,projection,manifestSha,sourceSha}) {
  need(selected?.kind === 'project-forge-native-stable-candidate-assembly' &&
    selected?.schemaVersion === 2 && selected.package === '@mriekki/project-forge' &&
    selected.version === '4.36.0' && selected.previousVersion === '4.35.0' &&
    selected.previousReceiptSha256 === RECEIPT && selected.sourceCommit === sourceSha &&
    selected.allowPublish === false && selected.allowProduction === false,
    'Selected stable identity mismatch');
  need(equal(Object.keys(prior.components).sort(),ids),'Incomplete prior component inventory');
  const expected = Object.fromEntries(ids.map(id=>[id,{
    revision:prior.components[id].revision,revisionKind:prior.components[id].revisionKind,
    mappedInputSha256:prior.components[id].mappedInputSha256
  }]));
  need(equal(selected.previousComponents,expected),'Selected prior identity mismatch');
  need(equal(evidence,{
    kind:'project-forge-native-stable-candidate-evidence',schemaVersion:2,
    sourceCommit:sourceSha,manifestSha256:manifestSha,packageVersion:'4.36.0',
    components:expected,changedComponents:[],releaseAuthorized:false,
    previousAcceptanceAuthenticatedHere:false,sourceOwnershipTransferred:false,
    published:false,productionAuthorized:false,previousVersion:'4.35.0',
    previousReceiptSha256:RECEIPT,archiveForm:'public-stable'
  }),'Stable assembly evidence differs');
  need(equal(Object.keys(projection.packageComponents).sort(),ids) &&
    equal(Object.keys(projection.assemblyRevisions).sort(),ids),'Archive component inventory differs');
  for (const id of ids) {
    need(projection.packageComponents[id].revision===expected[id].revision &&
      projection.assemblyRevisions[id]===expected[id].revision &&
      (id!=='core'||projection.packageComponents[id].version===prior.components[id].version),
      'Unexpected revision churn');
  }
  return Object.freeze({result:'SELECTED_STABLE_EVIDENCE_MATCH',releaseAuthorized:false,published:false,
    sourceOwnershipTransferred:false,productionAuthorized:false});
}

export function readVerifiedStableCandidate(dir) {
  const read = name => fs.readFileSync(path.join(dir,name));
  const json = name => JSON.parse(read(name));
  verifyHistoricalRun(json('pf-prior-public-run.json'),json('pf-prior-public-jobs.json'));
  const priorComputed = json('pf-prior-components.json');
  const current = json('pf-current-components.json');
  need(equal(Object.keys(priorComputed).sort(),ids) && equal(Object.keys(current).sort(),ids),
    'Mapped input inventory differs');
  const prior = verifyPriorRegistryArchive({
    receiptBytes:fs.readFileSync('release/receipts/4.35.0.json'),
    expectedVersion:'4.35.0',expectedSha256:RECEIPT,
    archiveBytes:read('pf-prior-registry/mriekki-project-forge-4.35.0.tgz'),
    registry:json('pf-prior-registry/registry.json'),platformSource:PREVIOUS_SOURCE,
    componentDigests:Object.fromEntries(ids.map(id=>[id,priorComputed[id].mappedInputSha256]))
  }).previous;
  for(const id of ids) {
    need(priorComputed[id].revision===prior.components[id].revision &&
      priorComputed[id].revisionKind===prior.components[id].revisionKind &&
      current[id]===prior.components[id].mappedInputSha256,'Independent mapped source changed');
  }
  const manifestBytes=read('pf-selected-stable-manifest.json');
  need(hash(manifestBytes)===MANIFEST,'Reviewed selection digest mismatch');
  const archive=read('mriekki-project-forge-4.36.0.tgz');
  const projection=readReleaseArchiveProjection({archiveBytes:archive,expectedVersion:'4.36.0',requirePublishableForm:true});
  compareStableEvidence({evidence:json('pf-selected-stable-evidence.json'),selected:JSON.parse(manifestBytes),
    prior,projection,manifestSha:MANIFEST,sourceSha:SOURCE});
  const parity=json('pf-first-stable-content.json');
  need(parity.result==='FIRST_NATIVE_STABLE_CONTENT_MATCH' &&
    parity.candidateSha256===hash(archive) && parity.releaseAuthorized===false &&
    parity.published===false && parity.sourceOwnershipTransferred===false &&
    parity.productionAuthorized===false,'First stable content evidence mismatch');
  return {prior, archive, projection, manifestBytes,
    priorInputs:{receiptBytes:fs.readFileSync('release/receipts/4.35.0.json'),
      archiveBytes:read('pf-prior-registry/mriekki-project-forge-4.35.0.tgz'),
      registry:json('pf-prior-registry/registry.json'),platformSource:PREVIOUS_SOURCE,
      componentDigests:Object.fromEntries(ids.map(id=>[id,priorComputed[id].mappedInputSha256]))},
    componentDigests:current};
}
function run(dir) {
  const {archive}=readVerifiedStableCandidate(dir);
  console.log('Verified exact selected stable candidate, historical registry archive and unchanged shipped content.');
  console.log('STABLE_CANDIDATE_SHA256='+hash(archive));
  console.log('CURRENT_SIGNATURE_REVERIFIED=false RELEASE_AUTHORIZED=false NPM_PUBLISHED=false SOURCE_OWNERSHIP_TRANSFERRED=false');
}

if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {run(process.argv[2]);} catch {console.error('Selected stable candidate admission refused');process.exitCode=2;}
}
