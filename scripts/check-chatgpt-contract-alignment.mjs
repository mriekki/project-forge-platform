import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadReleaseReceipt } from './release-receipt.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SHA40 = /^[0-9a-f]{40}$/;
const EXACT_SEMVER = /^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$/;
const PROFILE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

function failure(detail) {
  return {
    aligned: false,
    message: `PUBLIC CHATGPT CONTRACT ADVANCEMENT REQUIRED\n${detail}`,
  };
}

function positiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

export function evaluateAlignment(packageVersion, descriptor) {
  if (descriptor?.schemaVersion !== 1) {
    return failure(`Expected descriptor schemaVersion 1, found ${descriptor?.schemaVersion ?? '<missing>'}`);
  }
  if (descriptor?.channel !== 'stable') {
    return failure(`Expected stable contract channel, found ${descriptor?.channel ?? '<missing>'}`);
  }

  const contractVersion = descriptor?.contractVersion;
  if (!positiveInteger(contractVersion)) {
    return failure(`Invalid contractVersion: ${contractVersion ?? '<missing>'}`);
  }
  const expectedSnapshot = `chatgpt/contracts/v${contractVersion}`;
  if (descriptor?.snapshotPath !== expectedSnapshot) {
    return failure(`Expected snapshotPath ${expectedSnapshot}, found ${descriptor?.snapshotPath ?? '<missing>'}`);
  }

  const generation = descriptor?.generation;
  if (!generation || typeof generation !== 'object' || Array.isArray(generation)) {
    return failure('generation must be an object');
  }
  if (generation.manifestFilename !== 'PROJECT_BOOTSTRAP.json') {
    return failure(`Expected generation.manifestFilename PROJECT_BOOTSTRAP.json, found ${generation.manifestFilename ?? '<missing>'}`);
  }
  if (generation.package !== '@mriekki/project-forge') {
    return failure(`Expected generation.package @mriekki/project-forge, found ${generation.package ?? '<missing>'}`);
  }
  if (!EXACT_SEMVER.test(generation.packageVersion ?? '')) {
    return failure(`Public contract package version must be exact semantic version; found ${generation.packageVersion ?? '<missing>'}`);
  }
  if (generation.packageVersion !== packageVersion) {
    return failure(`Package version: ${packageVersion}\nPublic contract package version: ${generation.packageVersion ?? '<missing>'}`);
  }
  if (!PROFILE.test(generation.profile ?? '')) {
    return failure(`Invalid generation.profile: ${generation.profile ?? '<missing>'}`);
  }

  const bootstrap = generation.bootstrap;
  if (!bootstrap || typeof bootstrap !== 'object' || Array.isArray(bootstrap)) {
    return failure('generation.bootstrap must be an object');
  }
  const forbiddenBootstrapFields = ['repository', 'commit', 'sourceRepository', 'sourceRepositoryUrl'];
  const leaked = forbiddenBootstrapFields.filter((field) => Object.hasOwn(bootstrap, field));
  if (leaked.length) {
    return failure(`generation.bootstrap exposes private source topology fields: ${leaked.join(', ')}`);
  }
  if (!SHA40.test(bootstrap.revision ?? '')) {
    return failure(`generation.bootstrap.revision must be an exact lowercase 40-character revision; found ${bootstrap.revision ?? '<missing>'}`);
  }
  if (!positiveInteger(bootstrap.protocolVersion)) {
    return failure(`Invalid generation.bootstrap.protocolVersion: ${bootstrap.protocolVersion ?? '<missing>'}`);
  }
  if (!positiveInteger(bootstrap.catalogVersion)) {
    return failure(`Invalid generation.bootstrap.catalogVersion: ${bootstrap.catalogVersion ?? '<missing>'}`);
  }
  if (generation.bootstrapProtocolVersion !== bootstrap.protocolVersion) {
    return failure(
      `generation.bootstrapProtocolVersion ${generation.bootstrapProtocolVersion ?? '<missing>'} does not match generation.bootstrap.protocolVersion ${bootstrap.protocolVersion}`,
    );
  }

  return {
    aligned: true,
    message: `Public ChatGPT contract: ALIGNED (${packageVersion}; Bootstrap ${bootstrap.revision})`,
  };
}

export async function checkRepository(repositoryRoot = root) {
  const packageJson = JSON.parse(await readFile(path.join(repositoryRoot, 'package.json'), 'utf8'));
  const descriptor = JSON.parse(await readFile(path.join(repositoryRoot, 'chatgpt/current.json'), 'utf8'));
  const alignment = evaluateAlignment(packageJson.version, descriptor);
  if (!alignment.aligned) {
    return alignment;
  }

  try {
    await loadReleaseReceipt(descriptor.generation.packageVersion, repositoryRoot);
  } catch (error) {
    return failure(`Durable release receipt: ${error.message}`);
  }

  return {
    aligned: true,
    message: `${alignment.message}; durable release receipt verified`,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await checkRepository();
  if (result.aligned) {
    console.log(result.message);
  } else {
    console.error(result.message);
    process.exitCode = 1;
  }
}
