/**
 * Offline successor admission projection, deliberately separate from the
 * exact first-release workflow and publisher. The protected caller must
 * authenticate the prior v2 receipt, registry archive, source/ancestry and
 * qualification run, and independently rebuild the candidate archive.
 * Matching projections here never grants publication or deployment authority.
 */
import {createHash} from 'node:crypto';
import {isDeepStrictEqual as equal} from 'node:util';

const PKG = '@mriekki/project-forge';
const IDS = ['authentication','core','deployment','feedback','release-notes'];
const SHA = /^[0-9a-f]{40}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const STABLE = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const ORIGINAL = 'original-owner-git-commit';
const NATIVE = 'private-monorepo-git-commit';
const need = (ok,message) => { if (!ok) throw new Error(message); };
const exact = (value,pattern) => typeof value === 'string' && pattern.test(value);
function fields(value,keys,label) {
  need(value && typeof value === 'object' && !Array.isArray(value) &&
    equal(Object.keys(value).sort(), [...keys].sort()), 'Invalid '+label);
}
function advancing(next,previous) {
  need(exact(next,STABLE) && exact(previous,STABLE),'Exact stable versions required');
  const a=next.split('.').map(BigInt), b=previous.split('.').map(BigInt);
  for(let i=0;i<3;i++) if(a[i]!==b[i]) return a[i]>b[i];
  return false;
}
function record(id,item) {
  fields(item,['revision','revisionKind','mappedInputSha256',...(id==='core'?['version']:[])],
    'prior component');
  need(exact(item.revision,SHA) && [ORIGINAL,NATIVE].includes(item.revisionKind) &&
    exact(item.mappedInputSha256,DIGEST) &&
    (id!=='core'||exact(item.version,STABLE)), 'Invalid prior component identity');
  return {revision:item.revision,revisionKind:item.revisionKind,mappedInputSha256:item.mappedInputSha256};
}

export function compareSuccessorEvidence({manifestBytes,prior,observed,evidence,projection}) {
  fields(prior,['version','receiptSha256','components'],'prior acceptance projection');
  fields(observed,['targetVersion','sourceCommit','previousSourceCommit','historicalSourceCommit',
    'shellTree','manifestSha256','componentDigests','coreVersion'],'independent source observations');
  need(Buffer.isBuffer(manifestBytes) && manifestBytes.length>0 && manifestBytes.length<=1024*1024 &&
    exact(observed.manifestSha256,DIGEST) &&
    createHash('sha256').update(manifestBytes).digest('hex')===observed.manifestSha256,
    'Reviewed manifest bytes differ');
  need(exact(prior.receiptSha256,DIGEST) && advancing(observed.targetVersion,prior.version),
    'Invalid predecessor or successor version');
  for(const key of ['sourceCommit','previousSourceCommit','historicalSourceCommit','shellTree'])
    need(exact(observed[key],SHA),'Exact independent source identity required');
  need(exact(observed.coreVersion,STABLE),'Exact observed Core compatibility version required');
  fields(prior.components,IDS,'prior component inventory');
  fields(observed.componentDigests,IDS,'independent mapped digests');
  const old=Object.fromEntries(IDS.map(id=>[id,record(id,prior.components[id])]));
  const selected=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(manifestBytes));
  const expectedSelection={schemaVersion:2,kind:'project-forge-native-stable-candidate-assembly',
    package:PKG,version:observed.targetVersion,previousVersion:prior.version,
    previousReceiptSha256:prior.receiptSha256,sourceCommit:observed.sourceCommit,
    previousSourceCommit:observed.previousSourceCommit,historicalSourceCommit:observed.historicalSourceCommit,
    shellTree:observed.shellTree,previousComponents:old,allowPublish:false,allowProduction:false};
  need(equal(selected,expectedSelection),'Selected successor identity differs');
  const next={}, changed=[];
  for(const id of IDS) {
    const digest=observed.componentDigests[id];
    need(exact(digest,DIGEST),'Invalid independently computed mapped digest');
    if(digest===old[id].mappedInputSha256) next[id]={...old[id]};
    else {
      need(observed.sourceCommit!==old[id].revision,'Changed content needs distinct native revision');
      next[id]={revision:observed.sourceCommit,revisionKind:NATIVE,mappedInputSha256:digest};
      changed.push(id);
    }
  }
  need(changed.includes('core') || observed.coreVersion===prior.components.core.version,
    'Unchanged Core compatibility version differs');
  need(equal(evidence,{schemaVersion:2,kind:'project-forge-native-stable-candidate-evidence',
    sourceCommit:observed.sourceCommit,manifestSha256:observed.manifestSha256,
    packageVersion:observed.targetVersion,components:next,changedComponents:changed,
    previousVersion:prior.version,previousReceiptSha256:prior.receiptSha256,archiveForm:'public-stable',
    releaseAuthorized:false,previousAcceptanceAuthenticatedHere:false,sourceOwnershipTransferred:false,
    published:false,productionAuthorized:false}),'Successor assembly evidence differs');
  need(equal(projection.package,{name:PKG,version:observed.targetVersion}),'Archive package differs');
  fields(projection.packageComponents,IDS,'archive component inventory');
  fields(projection.assemblyRevisions,IDS,'archive assembly inventory');
  for(const id of IDS) {
    const expected=id==='core'?{revision:next[id].revision,version:observed.coreVersion}:{revision:next[id].revision};
    need(equal(projection.packageComponents[id],expected) &&
      projection.assemblyRevisions[id]===next[id].revision,'Candidate archive component identity differs');
  }
  const components=structuredClone(next);
  components.core.version=observed.coreVersion;
  return {result:'NATIVE_SUCCESSOR_EVIDENCE_MATCH',components,changedComponents:changed,
    priorReceiptAuthenticatedHere:false,sourceEvidenceAuthenticatedHere:false,
    releaseAuthorized:false,published:false,sourceOwnershipTransferred:false,productionAuthorized:false};
}
