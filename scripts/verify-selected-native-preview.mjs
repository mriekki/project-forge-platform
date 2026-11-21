/** First exact native candidate preview. No release authority. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {isDeepStrictEqual as equal} from 'node:util';
import {pathToFileURL} from 'node:url';
import {verifyPriorRegistryArchive} from './prior-registry-archive.mjs';

const SOURCE = '5596f4de502935c4c4f04f8b1a261333416f7efb';
const MANIFEST_SHA = 'a3936e8f9964c9b9c44c025dc04e0ddea40cfdb064d332ff172a5e090451d153';
const RECEIPT_SHA = '9541dd1b7db4208e8407f6148515aa9f9c39dc38fbaa018bd24bd48d04a58009';
const PUBLIC_SOURCE = 'a5ebca39bae777aaf81ad29fb50d92cdcfa0c272';
const VERSION = '4.36.0-preview.7';
const PKG = '@mriekki/project-forge';
const ids = ['authentication','core','deployment','feedback','release-notes'];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const need = (ok, msg) => { if (!ok) throw new Error(msg); };

export function verifyHistoricalRun(run, jobs) {
  need(run?.id === 44646438478 && run.run_attempt === 1 &&
    run.head_sha === PUBLIC_SOURCE && run.head_branch === 'main' &&
    run.path === '.github/workflows/npm-publish.yml' && run.event === 'issues' &&
    run.status === 'completed' && run.conclusion === 'success' &&
    run.repository?.id === 1420848802 && run.actor?.id === 12054121 &&
    run.triggering_actor?.id === 12054121, 'Historical publication run mismatch');
  const matches = jobs?.jobs?.filter(j => j.name === 'publish') ?? [];
  need(jobs.total_count === 1 && matches.length === 1 &&
    matches[0].run_id === run.id && matches[0].run_attempt === 1 &&
    matches[0].conclusion === 'success', 'Historical publication job mismatch');
  for (const name of ['Verify authorized Project Forge Platform source',
    'Verify exact post-merge Platform CI','Verify exact private source checkouts',
    'Prepare reproducible release candidate','Verify release manifest matches authorization',
    'Publish exact package with npm Trusted Publishing','Resolve signed provenance evidence',
    'Verify published registry identity','Verify public package from neutral directory',
    'Record machine-readable publication evidence']) {
    const steps = matches[0].steps.filter(s => s.name === name);
    need(steps.length === 1 && steps[0].conclusion === 'success', 'Historical publication step incomplete');
  }
}
export function verifySelectedProjection({manifestBytes, evidence, previous, pkg, meta, assembly}) {
  need(hash(manifestBytes) === MANIFEST_SHA, 'Selection digest mismatch');
  const manifest = JSON.parse(manifestBytes);
  need(manifest.sourceCommit === SOURCE && manifest.version === VERSION &&
    manifest.allowPublish === false && manifest.allowProduction === false, 'Selection identity mismatch');
  need(equal(Object.keys(previous.components).sort(), ids), 'Prior component inventory mismatch');
  const expected = {};
  for (const id of ids) {
    const r = previous.components[id];
    expected[id] = {revision:r.revision,revisionKind:r.revisionKind,mappedInputSha256:r.mappedInputSha256};
  }
  need(equal(expected,manifest.previousComponents), 'Selected prior components differ');
  need(equal(evidence, {kind:'project-forge-native-manifest-preview',schemaVersion:2,
    sourceCommit:SOURCE,manifestSha256:MANIFEST_SHA,packageVersion:VERSION,components:expected,
    changedComponents:[],releaseAuthorized:false,previousAcceptanceAuthenticatedHere:false,
    sourceOwnershipTransferred:false,published:false,productionAuthorized:false}), 'Candidate evidence differs');
  need(pkg?.name === PKG && pkg.version === VERSION && pkg.private === true &&
    meta?.schemaVersion === 2 && meta.package === PKG && meta.version === VERSION &&
    assembly?.schemaVersion === 2 && assembly.package === PKG && assembly.version === VERSION,
    'Unpublished package metadata mismatch');
  for (const records of [meta.components,assembly.components]) {
    need(equal(Object.keys(records).sort(),ids), 'Archive component inventory mismatch');
    for (const id of ids) need(records[id].revision === expected[id].revision &&
      (id !== 'core' || records[id].version === previous.components[id].version), 'Archive revision mismatch');
  }
}
function archiveJson(archive, name) {
  return JSON.parse(execFileSync('tar',['-xOzf','-', 'package/'+name],
    {input:archive,maxBuffer:8*1024*1024,timeout:15000,stdio:['pipe','pipe','pipe']}));
}
function run(dir) {
  const read = name => fs.readFileSync(path.join(dir,name));
  const json = name => JSON.parse(read(name));
  verifyHistoricalRun(json('pf-prior-public-run.json'),json('pf-prior-public-jobs.json'));
  const computed = json('pf-prior-components.json');
  need(equal(Object.keys(computed).sort(), ids),'Prior digest inventory mismatch');
  const prior = verifyPriorRegistryArchive({
    receiptBytes:fs.readFileSync('release/receipts/4.35.0.json'),
    expectedVersion:'4.35.0',expectedSha256:RECEIPT_SHA,
    archiveBytes:read('pf-prior-registry/mriekki-project-forge-4.35.0.tgz'),
    registry:json('pf-prior-registry/registry.json'),platformSource:PUBLIC_SOURCE,
    componentDigests:Object.fromEntries(ids.map(id=>[id,computed[id].mappedInputSha256]))
  });
  for (const id of ids) need(computed[id].revision === prior.previous.components[id].revision &&
    computed[id].revisionKind === prior.previous.components[id].revisionKind, 'Historical source revision mismatch');
  const archive = read('mriekki-project-forge-'+VERSION+'.tgz');
  need(archive.length > 0 && archive.length <= 32*1024*1024, 'Invalid preview archive size');
  verifySelectedProjection({manifestBytes:read('pf-selected-manifest.json'),
    evidence:json('pf-selected-evidence.json'),previous:prior.previous,
    pkg:archiveJson(archive,'package.json'),meta:archiveJson(archive,'assets/components.json'),
    assembly:archiveJson(archive,'assets/generated/ASSEMBLY.json')});
  console.log('Verified selected unpublished native candidate; prior registry bytes and historical publication run matched.');
  console.log('PREVIEW_ARCHIVE_SHA256='+hash(archive));
  console.log('CURRENT_SIGNATURE_REVERIFIED=false RELEASE_AUTHORIZED=false SOURCE_OWNERSHIP_TRANSFERRED=false NPM_PUBLISHED=false');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { run(process.argv[2]); } catch { console.error('Selected native preview verification refused'); process.exitCode=2; }
}
