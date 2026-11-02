import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const MANIFEST_RELATIVES = [
  'assets/bootstrap-migrations/managed-baseline-verifier/manifest.json',
  'assets/bootstrap-migrations/wsl-setup/setup-launcher.manifest.json',
  'assets/bootstrap-migrations/wsl-setup/setup-wsl.manifest.json'
];
const BOOTSTRAP_MANIFEST = 'PROJECT_BOOTSTRAP.json';

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

export function gitBlobSha(data) {
  const raw = Buffer.isBuffer(data) ? data : Buffer.from(data);
  const buffer = Buffer.from(raw.toString('utf8').replaceAll('\r\n', '\n'), 'utf8');
  const header = Buffer.from(`blob ${buffer.length}\0`, 'utf8');
  return crypto.createHash('sha1').update(header).update(buffer).digest('hex');
}

function safeRelative(value, label) {
  if (typeof value !== 'string' || !value || path.isAbsolute(value)) {
    throw new Error(`Unsafe ${label}: ${value}`);
  }
  const normalized = value.replaceAll('\\', '/');
  if (normalized.split('/').some((part) => !part || part === '.' || part === '..')) {
    throw new Error(`Unsafe ${label}: ${value}`);
  }
  return normalized;
}

function safeConsumerPath(root, relative) {
  const normalized = safeRelative(relative, 'Bootstrap migration destination');
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(resolvedRoot, ...normalized.split('/'));
  if (resolved !== resolvedRoot && !resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`Unsafe Bootstrap migration destination: ${relative}`);
  }
  return resolved;
}

function assertSafeExistingPath(root, destination, relative, kind = 'file') {
  const stat = fs.lstatSync(destination);
  if (kind === 'file' && (!stat.isFile() || stat.isSymbolicLink())) {
    throw new Error(`Bootstrap migration destination is not a regular file: ${relative}`);
  }
  if (kind === 'directory' && (!stat.isDirectory() || stat.isSymbolicLink())) {
    throw new Error(`Bootstrap migration parent is not a regular directory: ${relative}`);
  }
  const realRoot = fs.realpathSync(root);
  const realDestination = fs.realpathSync(destination);
  if (realDestination !== realRoot && !realDestination.startsWith(`${realRoot}${path.sep}`)) {
    throw new Error(`Bootstrap migration path resolves outside the Project root: ${relative}`);
  }
}

function loadManifest(packageData, manifestRelative) {
  const file = path.join(packageData.root, ...manifestRelative.split('/'));
  const manifest = readJson(file);
  if (manifest.schemaVersion !== 1 || manifest.owner !== 'bootstrap') {
    throw new Error('Invalid Bootstrap migration manifest ownership/schema');
  }
  if (manifest.source?.component !== 'bootstrap') {
    throw new Error('Invalid Bootstrap migration logical source component');
  }
  if (!/^[0-9a-f]{40}$/.test(manifest.source?.revision ?? '')) {
    throw new Error('Invalid Bootstrap migration source revision');
  }
  safeRelative(manifest.source?.artifact, 'Bootstrap migration source artifact');
  if (!/^[0-9a-f]{40}$/.test(manifest.targetGitBlob ?? '')) {
    throw new Error('Invalid Bootstrap migration target Git blob');
  }
  if (!Array.isArray(manifest.supportedPredecessorGitBlobs) || !manifest.supportedPredecessorGitBlobs.every((value) => /^[0-9a-f]{40}$/.test(value))) {
    throw new Error('Invalid Bootstrap migration predecessor identities');
  }
  if (manifest.supportedBootstrapRevisions !== undefined && (
    !Array.isArray(manifest.supportedBootstrapRevisions)
    || !manifest.supportedBootstrapRevisions.every((value) => /^[0-9a-f]{40}$/.test(value))
  )) {
    throw new Error('Invalid Bootstrap migration supported Bootstrap revisions');
  }
  if (manifest.allowMissing !== undefined && typeof manifest.allowMissing !== 'boolean') {
    throw new Error('Invalid Bootstrap migration allowMissing value');
  }
  const assetRelative = safeRelative(manifest.asset, 'Bootstrap migration bundled asset');
  const asset = path.join(packageData.root, ...assetRelative.split('/'));
  const bytes = fs.readFileSync(asset);
  if (gitBlobSha(bytes) !== manifest.targetGitBlob) {
    throw new Error(`Bundled Bootstrap migration asset identity does not match its manifest: ${manifest.id}`);
  }
  return { manifest, bytes };
}

function loadManifests(packageData) {
  return MANIFEST_RELATIVES.map((relative) => loadManifest(packageData, relative));
}

function appliesToBootstrap(manifest, bootstrap) {
  if (!manifest.supportedBootstrapRevisions) return true;
  const revision = bootstrap?.bootstrap?.commit;
  return typeof revision === 'string' && manifest.supportedBootstrapRevisions.includes(revision);
}

function migrationState(manifest) {
  return manifest.id === 'bootstrap-managed-baseline-verifier-schema2'
    ? 'MIGRATE_BOOTSTRAP_VERIFIER'
    : 'MIGRATE_BOOTSTRAP_FILE';
}

export function planBootstrapMigrations(packageData, consumerRoot) {
  const bootstrapManifest = path.join(consumerRoot, BOOTSTRAP_MANIFEST);
  if (!fs.existsSync(bootstrapManifest)) return { rows: [], unsafe: [] };

  const bootstrap = readJson(bootstrapManifest);
  const rows = [];
  const unsafe = [];

  for (const { manifest } of loadManifests(packageData)) {
    if (!appliesToBootstrap(manifest, bootstrap)) continue;

    const destination = safeConsumerPath(consumerRoot, manifest.destination);
    if (!fs.existsSync(destination)) {
      if (manifest.allowMissing) {
        const parent = path.dirname(destination);
        try {
          if (!fs.existsSync(parent)) throw new Error('parent missing');
          assertSafeExistingPath(consumerRoot, parent, path.dirname(manifest.destination), 'directory');
          rows.push({
            owner: 'bootstrap',
            state: 'ADD_BOOTSTRAP_FILE',
            path: manifest.destination,
            fromGitBlob: null,
            toGitBlob: manifest.targetGitBlob,
            source: manifest.source
          });
        } catch {
          unsafe.push({
            owner: 'bootstrap',
            state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
            path: manifest.destination,
            detail: 'Bootstrap migration parent is missing, unsafe, or resolves outside the Project root.'
          });
        }
        continue;
      }
      unsafe.push({
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: 'Bootstrap-generated file is missing; refusing package mutation before a supported migration is established.'
      });
      continue;
    }

    try {
      assertSafeExistingPath(consumerRoot, destination, manifest.destination, 'file');
    } catch (error) {
      unsafe.push({
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: `${error.message}; refusing package mutation.`
      });
      continue;
    }

    const currentGitBlob = gitBlobSha(fs.readFileSync(destination));
    if (currentGitBlob === manifest.targetGitBlob) continue;
    if (!manifest.supportedPredecessorGitBlobs.includes(currentGitBlob)) {
      unsafe.push({
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: `Unknown/custom Bootstrap file identity ${currentGitBlob}; refusing to overwrite it.`
      });
      continue;
    }

    rows.push({
      owner: 'bootstrap',
      state: migrationState(manifest),
      path: manifest.destination,
      fromGitBlob: currentGitBlob,
      toGitBlob: manifest.targetGitBlob,
      source: manifest.source
    });
  }

  return { rows, unsafe };
}

export function applyBootstrapMigrations(packageData, migrationPlan, consumerRoot) {
  if (!migrationPlan?.rows?.length) return;
  if (migrationPlan.unsafe?.length) throw new Error('Refusing unsafe Bootstrap migration plan');

  const byPath = new Map(loadManifests(packageData).map((entry) => [entry.manifest.destination, entry]));
  for (const row of migrationPlan.rows) {
    const entry = byPath.get(row.path);
    if (!entry) throw new Error(`Unsupported Bootstrap migration row path: ${row.path}`);
    const { manifest, bytes } = entry;
    if (!['MIGRATE_BOOTSTRAP_VERIFIER', 'MIGRATE_BOOTSTRAP_FILE', 'ADD_BOOTSTRAP_FILE'].includes(row.state)) {
      throw new Error(`Unsupported Bootstrap migration row: ${row.state ?? 'unknown'}`);
    }

    const destination = safeConsumerPath(consumerRoot, row.path);
    if (row.state === 'ADD_BOOTSTRAP_FILE') {
      if (!manifest.allowMissing || fs.existsSync(destination)) {
        throw new Error(`Bootstrap file changed after preview: ${row.path}`);
      }
      const parent = path.dirname(destination);
      if (!fs.existsSync(parent)) throw new Error(`Bootstrap migration parent changed after preview: ${row.path}`);
      assertSafeExistingPath(consumerRoot, parent, path.dirname(row.path), 'directory');
      fs.writeFileSync(destination, bytes);
    } else {
      if (!fs.existsSync(destination)) throw new Error(`Bootstrap file changed after preview: ${row.path}`);
      assertSafeExistingPath(consumerRoot, destination, row.path, 'file');
      const currentGitBlob = gitBlobSha(fs.readFileSync(destination));
      if (currentGitBlob !== row.fromGitBlob || !manifest.supportedPredecessorGitBlobs.includes(currentGitBlob)) {
        throw new Error(`Bootstrap file changed after preview: ${row.path}`);
      }
      fs.writeFileSync(destination, bytes);
    }

    if (gitBlobSha(fs.readFileSync(destination)) !== manifest.targetGitBlob) {
      throw new Error(`Bootstrap migration verification failed: ${row.path}`);
    }
  }
}
