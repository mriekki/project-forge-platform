import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const MANIFEST_RELATIVE = 'assets/bootstrap-migrations/managed-baseline-verifier/manifest.json';
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

function loadManifest(packageData) {
  const file = path.join(packageData.root, ...MANIFEST_RELATIVE.split('/'));
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
  const assetRelative = safeRelative(manifest.asset, 'Bootstrap migration bundled asset');
  const asset = path.join(packageData.root, ...assetRelative.split('/'));
  const bytes = fs.readFileSync(asset);
  if (gitBlobSha(bytes) !== manifest.targetGitBlob) {
    throw new Error('Bundled Bootstrap migration asset identity does not match its manifest');
  }
  return { manifest, bytes };
}

export function planBootstrapMigrations(packageData, consumerRoot) {
  const bootstrapManifest = path.join(consumerRoot, BOOTSTRAP_MANIFEST);
  if (!fs.existsSync(bootstrapManifest)) return { rows: [], unsafe: [] };

  const { manifest } = loadManifest(packageData);
  const destination = safeConsumerPath(consumerRoot, manifest.destination);
  if (!fs.existsSync(destination)) {
    return {
      rows: [],
      unsafe: [{
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: 'Bootstrap-generated verifier is missing; refusing package mutation before a supported migration is established.'
      }]
    };
  }

  const stat = fs.lstatSync(destination);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    return {
      rows: [],
      unsafe: [{
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: 'Bootstrap-generated verifier is not a regular file; refusing package mutation.'
      }]
    };
  }
  const realRoot = fs.realpathSync(consumerRoot);
  const realDestination = fs.realpathSync(destination);
  if (realDestination !== realRoot && !realDestination.startsWith(`${realRoot}${path.sep}`)) {
    return {
      rows: [],
      unsafe: [{
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: 'Bootstrap-generated verifier resolves outside the Project root; refusing package mutation.'
      }]
    };
  }

  const currentGitBlob = gitBlobSha(fs.readFileSync(destination));
  if (currentGitBlob === manifest.targetGitBlob) return { rows: [], unsafe: [] };
  if (!manifest.supportedPredecessorGitBlobs.includes(currentGitBlob)) {
    return {
      rows: [],
      unsafe: [{
        owner: 'bootstrap',
        state: 'BOOTSTRAP_MIGRATION_UNSUPPORTED',
        path: manifest.destination,
        detail: `Unknown/custom Bootstrap verifier identity ${currentGitBlob}; refusing to overwrite it.`
      }]
    };
  }

  return {
    rows: [{
      owner: 'bootstrap',
      state: 'MIGRATE_BOOTSTRAP_VERIFIER',
      path: manifest.destination,
      fromGitBlob: currentGitBlob,
      toGitBlob: manifest.targetGitBlob,
      source: manifest.source
    }],
    unsafe: []
  };
}

export function applyBootstrapMigrations(packageData, migrationPlan, consumerRoot) {
  if (!migrationPlan?.rows?.length) return;
  if (migrationPlan.unsafe?.length) throw new Error('Refusing unsafe Bootstrap migration plan');
  const { manifest, bytes } = loadManifest(packageData);
  for (const row of migrationPlan.rows) {
    if (row.state !== 'MIGRATE_BOOTSTRAP_VERIFIER' || row.path !== manifest.destination) {
      throw new Error(`Unsupported Bootstrap migration row: ${row.state ?? 'unknown'}`);
    }
    const destination = safeConsumerPath(consumerRoot, row.path);
    if (!fs.existsSync(destination) || fs.lstatSync(destination).isSymbolicLink() || !fs.lstatSync(destination).isFile()) {
      throw new Error(`Bootstrap verifier changed after preview: ${row.path}`);
    }
    const currentGitBlob = gitBlobSha(fs.readFileSync(destination));
    if (currentGitBlob !== row.fromGitBlob || !manifest.supportedPredecessorGitBlobs.includes(currentGitBlob)) {
      throw new Error(`Bootstrap verifier changed after preview: ${row.path}`);
    }
    fs.writeFileSync(destination, bytes);
    if (gitBlobSha(fs.readFileSync(destination)) !== manifest.targetGitBlob) {
      throw new Error(`Bootstrap verifier migration verification failed: ${row.path}`);
    }
  }
}
