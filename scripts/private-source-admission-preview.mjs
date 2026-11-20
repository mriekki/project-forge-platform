#!/usr/bin/env node
/**
 * Read-only private source admission PREVIEW for a previously published npm version.
 *
 * The caller must independently obtain repo/main/run JSON through authenticated
 * GitHub API requests made with a narrowly scoped protected source credential.
 * This does NOT authenticate arbitrary user-supplied JSON, authorize publication,
 * alter npm Trusted Publishing, or admit any unpublished version.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const SHA40 = /^[0-9a-f]{40}$/;
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const VERSION = '4.35.0';
const WORKFLOW_PATH = '.github/workflows/p0-main-release-qualification.yml';

function failUnless(value, reason) {
  if (!value) throw new Error(reason);
}

function integer(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function object(value) {
  return value && typeof value === 'object' && !Array.isArray(value);
}

export function validatePrivateSourceAdmissionPreview({
  selectedSourceSha,
  selectedSourceRunId,
  packageVersion,
  protectedSourceRepository,
  protectedSourceRepositoryId,
  sourceRepositoryMetadata,
  sourceMainRef,
  sourceQualificationRun
}) {
  failUnless(SHA40.test(selectedSourceSha), 'Exact selected source SHA is required');
  failUnless(integer(selectedSourceRunId), 'Exact successful source workflow run ID is required');
  failUnless(packageVersion === VERSION,
    'Only the previously published 4.35.0 parity fixture is supported by this nonpublishing preview');
  failUnless(typeof protectedSourceRepository === 'string' && REPO.test(protectedSourceRepository) &&
    integer(protectedSourceRepositoryId), 'Protected source repository mapping and immutable ID are required');

  const repo = sourceRepositoryMetadata;
  failUnless(object(repo) && repo.full_name === protectedSourceRepository &&
    repo.id === protectedSourceRepositoryId && repo.private === true &&
    repo.archived !== true && repo.default_branch === 'main',
  'Authenticated source repository identity does not match protected mapping');

  const ref = sourceMainRef;
  failUnless(object(ref) && ref.ref === 'refs/heads/main' &&
    object(ref.object) && ref.object.type === 'commit' &&
    ref.object.sha === selectedSourceSha,
  'Selected source SHA is not the latest authenticated private main commit');

  const run = sourceQualificationRun;
  failUnless(object(run) && run.id === selectedSourceRunId &&
    run.path === WORKFLOW_PATH && run.event === 'workflow_dispatch' &&
    run.head_sha === selectedSourceSha && run.head_branch === 'main' &&
    run.status === 'completed' && run.conclusion === 'success' &&
    integer(run.run_attempt) && integer(run.workflow_id) &&
    object(run.repository) && run.repository.id === protectedSourceRepositoryId &&
    object(run.head_repository) && run.head_repository.id === protectedSourceRepositoryId,
  'No successful completed full source release qualification at exact main SHA');
  failUnless(run.pull_requests === undefined || (
    Array.isArray(run.pull_requests) && run.pull_requests.length === 0
  ), 'PR-origin release qualification cannot establish exact main acceptance');

  return Object.freeze({
    schemaVersion: 1,
    kind: 'project-forge-private-source-admission-preview',
    result: 'EXACT_MAIN_AND_SOURCE_RUN_MATCH',
    packageVersion: VERSION,
    sourceSha: selectedSourceSha,
    sourceRunId: selectedSourceRunId,
    authenticatedSourceEvidence: 'caller-must-verify-github-rest',
    publishedVersionOnly: true,
    publicationAuthorized: false,
    sourceOwnershipTransferred: false,
    productionAuthorized: false
  });
}

export function parseAdmissionPreviewArgs(args) {
  const accepted = ['--source-sha','--source-run-id','--package-version',
    '--repository-json','--main-json','--run-json'];
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!accepted.includes(key) || Object.hasOwn(values,key) ||
      !args[index+1] || args[index+1].startsWith('--')) {
      throw new Error('Invalid source admission preview options');
    }
    values[key] = args[++index];
  }
  failUnless(Object.keys(values).length === accepted.length,
    'All exact source admission preview inputs are required');
  return values;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const a = parseAdmissionPreviewArgs(process.argv.slice(2));
    const selectedSourceRunId = Number(a['--source-run-id']);
    const protectedSourceRepositoryId = Number(process.env.PF_PROTECTED_SOURCE_REPOSITORY_ID);
    const maxJsonBytes = 1_000_000;
    function readJson(filename) {
      const stat = fs.lstatSync(filename);
      failUnless(stat.size > 0 && stat.size <= maxJsonBytes && !stat.isSymbolicLink(),
        'Invalid authenticated GitHub API evidence file');
      return JSON.parse(fs.readFileSync(filename, 'utf8'));
    }
    const result = validatePrivateSourceAdmissionPreview({
      selectedSourceSha: a['--source-sha'],
      selectedSourceRunId,
      packageVersion: a['--package-version'],
      protectedSourceRepository: process.env.PF_PROTECTED_SOURCE_REPOSITORY,
      protectedSourceRepositoryId,
      sourceRepositoryMetadata: readJson(a['--repository-json']),
      sourceMainRef: readJson(a['--main-json']),
      sourceQualificationRun: readJson(a['--run-json'])
    });
    console.log(JSON.stringify(result));
    console.log('SOURCE PREVIEW ONLY. Publication, source ownership and Production NOT AUTHORIZED.');
  } catch (error) {
    // Do not print source repo mapping, token, API JSON or arbitrary injected values.
    console.error('Private source admission preview REFUSED: ' + error.message);
    process.exitCode = 2;
  }
}
