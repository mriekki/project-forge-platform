import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  PASSKEY_SUPPORT_DESTINATION,
  PASSKEY_SUPPORT_SOURCE,
  verifyPasskeyCapability
} from '../src/passkey-capability.mjs';

const sources = [
  'src/ProjectForge.Auth.Runtime/ProjectAuthStore.Passkeys.cs',
  'src/ProjectForge.Auth.Runtime/ProjectAuthStore.PasskeyPolicy.cs',
  'src/ProjectForge.Auth.Runtime/ProjectPasskeyWebAuthn.cs',
  'src/ProjectForge.Auth.Runtime/ProjectForgePasskeyEndpoints.cs',
  'src/ProjectForge.Auth.Runtime/PasskeyVisibility.cs',
  'samples/ProjectForgeAuth.Api/wwwroot/passkeys.js',
  PASSKEY_SUPPORT_SOURCE
];

function support(state) {
  return {
    schemaVersion: 1,
    supportState: state,
    mode: 'passkey-first',
    relyingPartyId: 'exact-application-origin-host',
    userVerification: 'required',
    googleRecovery: true,
    enabledByDefault: false
  };
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-passkey-package-'));
  const packageData = {
    root,
    assets: {
      components: {
        authentication: { sourceRoot: 'assets/generated/authentication' }
      }
    }
  };
  const files = sources.map(source => ({
    source,
    destination: 'tools/project-forge-auth-kit/' + source,
    sha256: 'a'.repeat(64)
  }));
  const assembly = { components: { authentication: { files } } };
  const marker = path.join(root, 'assets/generated/authentication', PASSKEY_SUPPORT_SOURCE);
  fs.mkdirSync(path.dirname(marker), { recursive: true });
  const write = payload => fs.writeFileSync(marker, JSON.stringify(payload) + '\n');
  const cleanup = () => fs.rmSync(root, { recursive: true, force: true });
  return { root, packageData, assembly, files, marker, write, cleanup };
}

test('existing Google-only packages and non-auth profiles have no passkey claim', () => {
  const f = fixture();
  try {
    f.files.splice(f.files.findIndex(x => x.source === PASSKEY_SUPPORT_SOURCE), 1);
    assert.deepEqual(verifyPasskeyCapability(f.packageData, f.assembly), { state: 'not-present' });
    delete f.packageData.assets.components.authentication;
    assert.deepEqual(verifyPasskeyCapability(f.packageData, f.assembly), { state: 'not-present' });
  } finally { f.cleanup(); }
});

test('candidate is packaged but not qualified; only exact complete and safe marker is accepted', () => {
  const f = fixture();
  try {
    f.write(support('candidate'));
    assert.deepEqual(verifyPasskeyCapability(f.packageData, f.assembly), { state: 'candidate' });
    f.write(support('qualified'));
    assert.deepEqual(verifyPasskeyCapability(f.packageData, f.assembly), { state: 'qualified' });
    f.write({ ...support('qualified'), googleRecovery: false });
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /invalid or unsafe/);
    f.write({ ...support('qualified'), enabledByDefault: true });
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /invalid or unsafe/);
    f.write({ ...support('qualified'), extraClaim: 'ignore' });
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /invalid or unsafe/);
    f.write(support('unreviewed'));
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /invalid or unsafe/);
    fs.writeFileSync(f.marker, 'not-json');
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /not valid JSON/);
  } finally { f.cleanup(); }
});

test('marker cannot advertise incomplete or redirected managed WebAuthn files', () => {
  const f = fixture();
  try {
    f.write(support('qualified'));
    const source = 'src/ProjectForge.Auth.Runtime/ProjectForgePasskeyEndpoints.cs';
    const index = f.files.findIndex(x => x.source === source);
    const removed = f.files.splice(index, 1)[0];
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /incomplete/);
    f.files.push(removed);
    const marker = f.files.find(x => x.source === PASSKEY_SUPPORT_SOURCE);
    marker.destination = 'tools/incorrect/PASSKEY_SUPPORT.json';
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /unsupported managed destination/);
    marker.destination = PASSKEY_SUPPORT_DESTINATION;
    f.files.push({ ...marker });
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /incomplete/);
  } finally { f.cleanup(); }
});

test('support marker must be a regular packaged file, never a symlink or missing file', () => {
  const f = fixture();
  try {
    f.write(support('candidate'));
    fs.unlinkSync(f.marker);
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /missing or unsafe/);
    try {
      fs.symlinkSync('linked-source', f.marker);
    } catch (error) {
      if (error.code === 'EPERM' || error.code === 'EACCES') return;
      throw error;
    }
    assert.throws(() => verifyPasskeyCapability(f.packageData, f.assembly), /missing or unsafe/);
  } finally { f.cleanup(); }
});
