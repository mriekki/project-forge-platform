import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SHA40 = /^[0-9a-f]{40}$/;
const SHA1 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const EXACT_SEMVER = /^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$/;
const SIGSTORE_LOG = /^https:\/\/search\.sigstore\.dev\/\?logIndex=[0-9]+$/;

function positiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

function requireObject(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  return value;
}

function requireExact(value, expected, name) {
  if (value !== expected) {
    throw new Error(`${name} must equal ${expected}; found ${value ?? '<missing>'}`);
  }
}

function requireMatch(value, pattern, name) {
  if (typeof value !== 'string' || !pattern.test(value)) {
    throw new Error(`${name} is invalid: ${value ?? '<missing>'}`);
  }
}

function requireCiEvidence(value, name) {
  const evidence = requireObject(value, name);
  requireExact(evidence.result, 'success', `${name}.result`);
  if (!positiveInteger(evidence.workflowRunId)) {
    throw new Error(`${name}.workflowRunId must be a positive integer`);
  }
}

export function validateReleaseReceipt(receipt, expectedVersion = null) {
  const value = requireObject(receipt, 'release receipt');
  requireExact(value.schemaVersion, 1, 'schemaVersion');

  const packageInfo = requireObject(value.package, 'package');
  requireExact(packageInfo.name, '@mriekki/project-forge', 'package.name');
  requireMatch(packageInfo.version, EXACT_SEMVER, 'package.version');
  if (expectedVersion !== null) {
    requireExact(packageInfo.version, expectedVersion, 'package.version');
  }

  requireMatch(value.platformSource, SHA40, 'platformSource');

  const components = requireObject(value.components, 'components');
  const core = requireObject(components.core, 'components.core');
  requireMatch(core.revision, SHA40, 'components.core.revision');
  requireMatch(core.version, EXACT_SEMVER, 'components.core.version');
  const deployment = requireObject(components.deployment, 'components.deployment');
  requireMatch(deployment.revision, SHA40, 'components.deployment.revision');

  for (const component of [core, deployment]) {
    for (const forbidden of ['repository', 'sourceRepository', 'sourceRepositoryUrl', 'privateRepository']) {
      if (Object.hasOwn(component, forbidden)) {
        throw new Error(`release receipt exposes forbidden component source field ${forbidden}`);
      }
    }
  }

  const artifact = requireObject(value.artifact, 'artifact');
  requireMatch(artifact.releaseCandidateSha256, SHA256, 'artifact.releaseCandidateSha256');
  requireMatch(artifact.registryShasum, SHA1, 'artifact.registryShasum');

  const publication = requireObject(value.publication, 'publication');
  requireMatch(publication.publishedAt, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/, 'publication.publishedAt');
  if (!positiveInteger(publication.workflowRunId)) {
    throw new Error('publication.workflowRunId must be a positive integer');
  }
  requireExact(publication.publisher, 'github-oidc', 'publication.publisher');
  requireExact(publication.registryIdentity, 'verified', 'publication.registryIdentity');
  requireExact(publication.neutralNpxSmoke, 'verified', 'publication.neutralNpxSmoke');

  const provenance = requireObject(publication.provenance, 'publication.provenance');
  requireExact(provenance.signed, true, 'publication.provenance.signed');
  requireMatch(provenance.transparencyLogUrl, SIGSTORE_LOG, 'publication.provenance.transparencyLogUrl');

  const ci = requireObject(value.ci, 'ci');
  requireCiEvidence(ci.coreMain, 'ci.coreMain');
  requireCiEvidence(ci.deploymentMain, 'ci.deploymentMain');
  requireCiEvidence(ci.platformMain, 'ci.platformMain');

  return value;
}

export async function loadReleaseReceipt(version, repositoryRoot = root) {
  requireMatch(version, EXACT_SEMVER, 'version');
  const receiptPath = path.join(repositoryRoot, 'release', 'receipts', `${version}.json`);
  let parsed;
  try {
    parsed = JSON.parse(await readFile(receiptPath, 'utf8'));
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error(`Missing durable release receipt for @mriekki/project-forge@${version}`);
    }
    throw new Error(`Unable to read durable release receipt for @mriekki/project-forge@${version}: ${error.message}`);
  }
  return validateReleaseReceipt(parsed, version);
}

export async function resolvePublishedPlatformSource(version, repositoryRoot = root) {
  const receipt = await loadReleaseReceipt(version, repositoryRoot);
  return receipt.platformSource;
}

export function parseArgs(argv) {
  let version = null;
  let json = false;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--version') {
      version = argv[index + 1] ?? null;
      index += 1;
    } else if (arg === '--json') {
      json = true;
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }
  requireMatch(version, EXACT_SEMVER, 'version');
  return { version, json };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const options = parseArgs(process.argv.slice(2));
    const receipt = await loadReleaseReceipt(options.version);
    if (options.json) {
      console.log(JSON.stringify({
        package: receipt.package,
        platformSource: receipt.platformSource,
        components: receipt.components,
        artifact: receipt.artifact,
        publication: receipt.publication,
        ci: receipt.ci,
      }, null, 2));
    } else {
      console.log(`Durable release receipt: @mriekki/project-forge@${receipt.package.version}`);
      console.log(`Platform source: ${receipt.platformSource}`);
    }
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
