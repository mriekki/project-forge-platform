import fs from 'node:fs';
import { resolveUnder } from './engine.mjs';
import { readJson } from './package-data.mjs';

// Packaging guard only. A qualified marker is an independently reviewed
// release decision, NOT cryptographic proof and never enables Production.
export const PASSKEY_SUPPORT_SOURCE = 'docs/PASSKEY_SUPPORT.json';
export const PASSKEY_SUPPORT_DESTINATION =
  'tools/project-forge-auth-kit/docs/PASSKEY_SUPPORT.json';

const REQUIRED_PASSKEY_SOURCES = [
  'src/ProjectForge.Auth.Runtime/ProjectAuthStore.Passkeys.cs',
  'src/ProjectForge.Auth.Runtime/ProjectAuthStore.PasskeyPolicy.cs',
  'src/ProjectForge.Auth.Runtime/ProjectPasskeyWebAuthn.cs',
  'src/ProjectForge.Auth.Runtime/ProjectForgePasskeyEndpoints.cs',
  'src/ProjectForge.Auth.Runtime/PasskeyVisibility.cs',
  'samples/ProjectForgeAuth.Api/wwwroot/passkeys.js',
  PASSKEY_SUPPORT_SOURCE,
];

const expectedMarker = {
  schemaVersion: 1,
  mode: 'passkey-first',
  relyingPartyId: 'exact-application-origin-host',
  userVerification: 'required',
  googleRecovery: true,
  enabledByDefault: false,
};

const destinationOf = (source) =>
  'tools/project-forge-auth-kit/' + source;

/**
 * Check that an exact packaged Authentication component carries an honest,
 * self-consistent passkey support declaration and complete managed file set.
 *
 * This is called only AFTER ordinary assembly validation has checked the
 * pinned component revision, canonical descriptor, and every file SHA-256.
 * The presence of source code or a candidate marker does not advertise
 * selectable support, and never authorizes deployment or user enrollment.
 */
export function verifyPasskeyCapability(packageData, assembly) {
  const component = packageData.assets.components?.authentication;
  if (!component) return { state: 'not-present' };
  const files = assembly.components?.authentication?.files;
  if (!Array.isArray(files)) {
    throw new Error('Authentication component has no recorded package files');
  }
  const markerEntry = files.find((item) => item.source === PASSKEY_SUPPORT_SOURCE);
  if (!markerEntry) return { state: 'not-present' };
  if (markerEntry.destination !== PASSKEY_SUPPORT_DESTINATION) {
    throw new Error('Authentication passkey support marker has an unsupported managed destination');
  }

  const markerPath = resolveUnder(
    packageData.root,
    component.sourceRoot + '/' + PASSKEY_SUPPORT_SOURCE,
    'packaged Auth Kit passkey capability'
  );
  if (!fs.existsSync(markerPath) ||
      !fs.statSync(markerPath).isFile() ||
      fs.lstatSync(markerPath).isSymbolicLink()) {
    throw new Error('Packaged Auth Kit passkey support marker is missing or unsafe');
  }
  let marker;
  try {
    marker = readJson(markerPath);
  } catch {
    throw new Error('Packaged Auth Kit passkey support marker is not valid JSON');
  }
  if (!marker || typeof marker !== 'object' || Array.isArray(marker)) {
    throw new Error('Packaged Auth Kit passkey support marker must be an object');
  }

  const keys = Object.keys(expectedMarker).concat('supportState').sort();
  if (JSON.stringify(Object.keys(marker).sort()) !== JSON.stringify(keys) ||
      !['candidate', 'qualified'].includes(marker.supportState) ||
      Object.entries(expectedMarker).some(([key, value]) => marker[key] !== value)) {
    throw new Error('Packaged Auth Kit passkey support declaration is invalid or unsafe');
  }

  for (const source of REQUIRED_PASSKEY_SOURCES) {
    const matches = files.filter((item) => item.source === source);
    if (matches.length !== 1 || matches[0].destination !== destinationOf(source)) {
      throw new Error('Packaged Auth Kit passkey capability is incomplete: ' + source);
    }
  }
  return { state: marker.supportState };
}
