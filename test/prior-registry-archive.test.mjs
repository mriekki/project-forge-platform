import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { verifyPriorRegistryArchive } from '../scripts/prior-registry-archive.mjs';

const hash = (algorithm, bytes, encoding = 'hex') =>
  createHash(algorithm).update(bytes).digest(encoding);
const old = JSON.parse(fs.readFileSync(new URL('../release/receipts/4.35.0.json', import.meta.url)));
function fixture(change = () => {}) {
  const receipt = structuredClone(old);
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'pf-prior-archive-'));
  try {
    const metadata = {schemaVersion:2, package:receipt.package.name,
      version:receipt.package.version, components:structuredClone(receipt.components)};
    const docs = {
      'package.json':{...receipt.package},
      'assets/components.json':metadata,
      'assets/generated/ASSEMBLY.json':structuredClone(metadata)
    };
    change(docs);
    for (const [name,doc] of Object.entries(docs)) {
      const file = path.join(root,'package',name);
      fs.mkdirSync(path.dirname(file),{recursive:true});
      fs.writeFileSync(file,JSON.stringify(doc));
    }
    const archiveBytes = execFileSync('tar',['-czf','-','-C',root,'package']);
    receipt.artifact = {releaseCandidateSha256:hash('sha256',archiveBytes),
      registryShasum:hash('sha1',archiveBytes)};
    const receiptBytes = Buffer.from(JSON.stringify(receipt));
    return {receiptBytes,expectedVersion:'4.35.0',expectedSha256:hash('sha256',receiptBytes),
      archiveBytes,registry:{...receipt.package,dist:{shasum:receipt.artifact.registryShasum,
        integrity:'sha512-'+hash('sha512',archiveBytes,'base64')}},
      platformSource:receipt.platformSource,
      componentDigests:Object.fromEntries(Object.keys(receipt.components).map((id,i)=>[id,String(i+1).repeat(64)]))};
  } finally {
    fs.rmSync(root,{recursive:true,force:true});
  }
}
test('matching synthetic registry archive and exact receipt yield prior projection only',()=>{
  const result = verifyPriorRegistryArchive(fixture());
  assert.equal(result.previous.version,'4.35.0');
  assert.equal(result.previous.components.core.revisionKind,'original-owner-git-commit');
  for (const key of ['archiveReceiptMatched','registryIntegrityMatched']) assert.equal(result[key],true);
  for (const key of ['priorReceiptAuthenticatedHere','sourceEvidenceAuthenticatedHere',
    'signatureVerifiedHere','releaseAuthorized','sourceOwnershipTransferred','productionAuthorized'])
    assert.equal(result[key],false);
});
test('reject changed receipts, archive, registry, source evidence or missing mapped digest',()=>{
  for (const mutate of [
    x=>x.expectedSha256='0'.repeat(64),
    x=>x.archiveBytes=Buffer.concat([x.archiveBytes,Buffer.from('changed')]),
    x=>x.registry.name='wrong', x=>x.registry.version='4.36.0',
    x=>x.registry.dist.shasum='0'.repeat(40), x=>x.registry.dist.integrity='sha512-wrong',
    x=>x.platformSource='0'.repeat(40), x=>delete x.componentDigests.core
  ]) {
    const x=fixture();mutate(x);assert.throws(()=>verifyPriorRegistryArchive(x));
  }
});
test('reject incompatible package and component observations even when archive hashes agree',()=>{
  for (const mutate of [
    x=>x['package.json'].private=true,
    x=>x['package.json'].version='4.36.0',
    x=>x['assets/components.json'].components.core.version='99.0.0',
    x=>x['assets/generated/ASSEMBLY.json'].components.feedback.revision='0'.repeat(40),
    x=>delete x['assets/components.json'].components.feedback,
    x=>{
      x['assets/components.json'].components.feedback.revision='0'.repeat(40);
      x['assets/generated/ASSEMBLY.json'].components.feedback.revision='0'.repeat(40);
    }
  ]) assert.throws(()=>verifyPriorRegistryArchive(fixture(mutate)));
});
