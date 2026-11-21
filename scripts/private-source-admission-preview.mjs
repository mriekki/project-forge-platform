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
// Reviewed Git blob identities, not repository names or credentials.
// Changing either source contract requires a new reviewed preview admission policy.
const OWNER_ISSUE_WORKFLOW_BLOB = '13cda308770fb2f12cd70f130570cdb9daa6b88b';
const OWNER_ISSUE_IDENTITY_PATH = 'tools/release/verify_main_identity.py';
const OWNER_ISSUE_IDENTITY_BLOB = 'a7919cce83e31c11b506594481837dad5c86c10e';
const REQUIRED_OWNER_ISSUE_STEPS = Object.freeze([
  "Validate exact owner-issued nonpublishing source qualification request",
  "Checkout exact approved private source",
  "Set up Node 22 and Python 3.13",
  "Verify authenticated main and all seven immutable imported source trees",
  "Checkout public reference only for immutable historical parity, never for build inputs",
  "Checkout public receipt verifier (read-only)",
  "Qualify native npm 4.35.0 assets and package contract (no npm publish)",
  "Qualify original Core, Bootstrap and Adoption Python contracts",
  "Setup Python 3.11 and test-only cryptographic dependencies",
  "Qualify Deployment restore/recovery and all original Python contracts",
  "Setup .NET 10 and verify Authentication, Feedback, Release Notes runtime",
  "Qualify Authentication .NET and household contracts",
  "Qualify Feedback fake-GitHub integration (no live provider)",
  "Qualify Release Notes Python, .NET, and UI contracts",
  "Reverify current main SHA after all source qualifications"
]);

function failUnless(value, reason) {
  if (!value) throw new Error(reason);
}

function integer(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function object(value) {
  return value && typeof value === 'object' && !Array.isArray(value);
}

function validateOwnerIssueQualification({ repo, run, jobs, workflow, identity }) {
  // These inputs must come from the protected, independently authenticated REST
  // transport, not from an issue author, candidate archive, or log assertion.
  failUnless(integer(repo.owner?.id) && run.actor?.id === repo.owner.id &&
    run.triggering_actor?.id === repo.owner.id,
  'Owner-Issue qualification must be started and rerun by the authenticated source owner');
  for (const [file, expectedPath, expectedBlob] of [
    [workflow, WORKFLOW_PATH, OWNER_ISSUE_WORKFLOW_BLOB],
    [identity, OWNER_ISSUE_IDENTITY_PATH, OWNER_ISSUE_IDENTITY_BLOB]
  ]) {
    failUnless(object(file) && file.type === 'file' &&
      file.path === expectedPath && file.sha === expectedBlob,
    'Owner-Issue qualification code differs from the reviewed source contract');
  }
  failUnless(object(jobs) && jobs.total_count === 1 &&
    Array.isArray(jobs.jobs) && jobs.jobs.length === 1,
  'Exactly one authenticated qualification job is required for this run attempt');
  const job = jobs.jobs[0];
  failUnless(object(job) && integer(job.id) &&
    job.run_id === run.id && job.run_attempt === run.run_attempt &&
    job.head_sha === run.head_sha && job.head_branch === 'main' &&
    job.name === 'source-release-qualification' &&
    job.workflow_name === 'P0 Private Exact-Main Release Qualification (NO PUBLISH)' &&
    job.status === 'completed' && job.conclusion === 'success' &&
    Array.isArray(job.steps),
  'Owner-Issue qualification job identity or conclusion mismatch');
  const names = new Set();
  let previous = 0;
  for (const step of job.steps) {
    failUnless(object(step) && integer(step.number) && step.number > previous &&
      typeof step.name === 'string' && !names.has(step.name) &&
      step.status === 'completed' && step.conclusion === 'success',
    'Owner-Issue qualification contains failed, skipped, duplicate or unordered steps');
    names.add(step.name);
    previous = step.number;
  }
  let lastIndex = -1;
  for (const name of REQUIRED_OWNER_ISSUE_STEPS) {
    const index = job.steps.findIndex(step => step.name === name);
    failUnless(index > lastIndex, 'Owner-Issue qualification missing or reordered required step');
    lastIndex = index;
  }
}

export function validatePrivateSourceAdmissionPreview({
  selectedSourceSha,
  selectedSourceRunId,
  packageVersion,
  protectedSourceRepository,
  protectedSourceRepositoryId,
  sourceRepositoryMetadata,
  sourceMainRef,
  sourceQualificationRun,
  sourceQualificationJobs,
  sourceQualificationWorkflow,
  sourceIdentityVerifier
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
    run.path === WORKFLOW_PATH && ['workflow_dispatch', 'issues'].includes(run.event) &&
    run.head_sha === selectedSourceSha && run.head_branch === 'main' &&
    run.status === 'completed' && run.conclusion === 'success' &&
    integer(run.run_attempt) && integer(run.workflow_id) &&
    object(run.repository) && run.repository.id === protectedSourceRepositoryId &&
    object(run.head_repository) && run.head_repository.id === protectedSourceRepositoryId,
  'No successful completed full source release qualification at exact main SHA');
  failUnless(run.pull_requests === undefined || (
    Array.isArray(run.pull_requests) && run.pull_requests.length === 0
  ), 'PR-origin release qualification cannot establish exact main acceptance');

  if (run.event === 'issues') {
    validateOwnerIssueQualification({
      repo, run, jobs: sourceQualificationJobs, workflow: sourceQualificationWorkflow,
      identity: sourceIdentityVerifier
    });
  } else {
    failUnless(sourceQualificationJobs === undefined &&
      sourceQualificationWorkflow === undefined && sourceIdentityVerifier === undefined,
    'Unexpected owner-Issue evidence for manual qualification');
  }

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
  const required = ['--source-sha','--source-run-id','--package-version',
    '--repository-json','--main-json','--run-json'];
  const extra = ['--jobs-json','--workflow-json','--identity-json'];
  const accepted = [...required, ...extra];
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!accepted.includes(key) || Object.hasOwn(values,key) ||
      !args[index+1] || args[index+1].startsWith('--')) {
      throw new Error('Invalid source admission preview options');
    }
    values[key] = args[++index];
  }
  failUnless(required.every(key => Object.hasOwn(values, key)),
    'All exact source admission preview inputs are required');
  failUnless(extra.every(key => Object.hasOwn(values, key)) ||
    extra.every(key => !Object.hasOwn(values, key)),
  'Complete owner-Issue evidence group required');
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
      sourceQualificationRun: readJson(a['--run-json']),
      sourceQualificationJobs: a['--jobs-json'] ? readJson(a['--jobs-json']) : undefined,
      sourceQualificationWorkflow: a['--workflow-json'] ? readJson(a['--workflow-json']) : undefined,
      sourceIdentityVerifier: a['--identity-json'] ? readJson(a['--identity-json']) : undefined
    });
    console.log(JSON.stringify(result));
    console.log('SOURCE PREVIEW ONLY. Publication, source ownership and Production NOT AUTHORIZED.');
  } catch (error) {
    // Do not print source repo mapping, token, API JSON or arbitrary injected values.
    console.error('Private source admission preview REFUSED: ' + error.message);
    process.exitCode = 2;
  }
}
