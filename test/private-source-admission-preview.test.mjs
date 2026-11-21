import assert from 'node:assert/strict';
import test from 'node:test';
import { validatePrivateSourceAdmissionPreview, parseAdmissionPreviewArgs } from '../scripts/private-source-admission-preview.mjs';

const SHA = 'a'.repeat(40);
const REPO = 'fixture/private-source';
const ID = 8675309;

function fixture() {
  return {
    selectedSourceSha: SHA,
    selectedSourceRunId: 12345,
    packageVersion: '4.35.0',
    protectedSourceRepository: REPO,
    protectedSourceRepositoryId: ID,
    sourceRepositoryMetadata: {
      id: ID, full_name: REPO, private: true, archived: false, default_branch: 'main'
    },
    sourceMainRef: {
      ref: 'refs/heads/main', object: { type: 'commit', sha: SHA }
    },
    sourceQualificationRun: {
      id: 12345, path: '.github/workflows/p0-main-release-qualification.yml',
      event: 'workflow_dispatch', head_sha: SHA, head_branch: 'main',
      status: 'completed', conclusion: 'success', run_attempt: 1, workflow_id: 555,
      repository: { id: ID }, head_repository: { id: ID }, pull_requests: []
    }
  };
}

function rejects(mutator, reason) {
  const x = fixture();
  mutator(x);
  assert.throws(() => validatePrivateSourceAdmissionPreview(x), reason);
}

test('accepted historical source preview never asserts publication or ownership', () => {
  const x = fixture();
  const result = validatePrivateSourceAdmissionPreview(x);
  assert.equal(result.result, 'EXACT_MAIN_AND_SOURCE_RUN_MATCH');
  assert.equal(result.sourceSha, SHA);
  assert.equal(result.sourceRunId, 12345);
  assert.equal(result.publishedVersionOnly, true);
  assert.equal(result.publicationAuthorized, false);
  assert.equal(result.sourceOwnershipTransferred, false);
  assert.equal(result.productionAuthorized, false);
  assert.equal(result.authenticatedSourceEvidence, 'caller-must-verify-github-rest');
  assert.equal(JSON.stringify(result).includes(REPO), false);
});

test('protected mapping or stable repository ID mismatch refuses', () => {
  rejects(x => { x.protectedSourceRepository = ''; }, /Protected source/);
  rejects(x => { x.protectedSourceRepositoryId = null; }, /Protected source/);
  rejects(x => { x.sourceRepositoryMetadata.full_name = 'malicious/fork'; }, /repository identity/);
  rejects(x => { x.sourceRepositoryMetadata.id = 1; }, /repository identity/);
  rejects(x => { x.sourceRepositoryMetadata.private = false; }, /repository identity/);
  rejects(x => { x.sourceRepositoryMetadata.archived = true; }, /repository identity/);
  rejects(x => { x.sourceRepositoryMetadata.default_branch = 'develop'; }, /repository identity/);
});

test('missing, moving, incorrect, or noncommit main ref refuses', () => {
  rejects(x => { x.sourceMainRef.object.sha = 'b'.repeat(40); }, /latest authenticated/);
  rejects(x => { x.sourceMainRef.ref = 'refs/heads/feature'; }, /latest authenticated/);
  rejects(x => { x.sourceMainRef.object.type = 'tag'; }, /latest authenticated/);
  rejects(x => { x.selectedSourceSha = 'main'; }, /Exact selected/);
});

test('stale or misattributed full qualification run refuses', () => {
  rejects(x => { x.selectedSourceRunId = 42; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.head_sha = 'b'.repeat(40); }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.repository.id = 99; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.head_repository.id = 99; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.path = '.github/workflows/p0-main-source-preflight.yml'; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.event = 'pull_request'; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.head_branch = 'feature'; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.status = 'in_progress'; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.conclusion = 'failure'; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.workflow_id = null; }, /No successful completed/);
  rejects(x => { x.sourceQualificationRun.pull_requests = [{ id: 1 }]; }, /PR-origin/);
});

test('unpublished versions and arbitrary command-line omission are rejected', () => {
  rejects(x => { x.packageVersion = '4.36.0'; }, /only the previously published|previously published/);
  const args = ['--source-sha',SHA,'--source-run-id','12345','--package-version','4.35.0',
    '--repository-json','repo.json','--main-json','main.json','--run-json','run.json'];
  assert.deepEqual(parseAdmissionPreviewArgs(args)['--source-sha'], SHA);
  assert.throws(() => parseAdmissionPreviewArgs(args.slice(0, 4)), /required/);
  assert.throws(() => parseAdmissionPreviewArgs([...args, '--source-sha', SHA]), /Invalid/);
});

const OWNER = 987654;
function issueFixture() {
  const x = fixture();
  x.sourceRepositoryMetadata.owner = { id: OWNER };
  Object.assign(x.sourceQualificationRun, {
    event: 'issues', actor: { id: OWNER }, triggering_actor: { id: OWNER }
  });
  x.sourceQualificationWorkflow = {
    path: '.github/workflows/p0-main-release-qualification.yml',
    type: 'file', sha: '13cda308770fb2f12cd70f130570cdb9daa6b88b'
  };
  x.sourceIdentityVerifier = {
    path: 'tools/release/verify_main_identity.py',
    type: 'file', sha: 'a7919cce83e31c11b506594481837dad5c86c10e'
  };
  const names = [
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
];
  x.sourceQualificationJobs = {
    total_count: 1, jobs: [{
      id: 1234, run_id: 12345, run_attempt: 1, head_sha: SHA, head_branch: 'main',
      name: 'source-release-qualification',
      workflow_name: 'P0 Private Exact-Main Release Qualification (NO PUBLISH)',
      status: 'completed', conclusion: 'success',
      steps: names.map((name, i) => ({
        name, number: i+1, status: 'completed', conclusion: 'success'
      }))
    }]
  };
  return x;
}
function issueReject(mutate, reason) {
  const x = issueFixture();
  mutate(x);
  assert.throws(() => validatePrivateSourceAdmissionPreview(x), reason);
}

test('reviewed exact owner-Issue qualification admits only a nonpublishing preview', () => {
  const x = issueFixture();
  const result = validatePrivateSourceAdmissionPreview(x);
  assert.equal(result.result, 'EXACT_MAIN_AND_SOURCE_RUN_MATCH');
  for (const key of ['publicationAuthorized','sourceOwnershipTransferred','productionAuthorized']) {
    assert.equal(result[key], false);
  }
  assert.equal(JSON.stringify(result).includes(REPO), false);
});

test('owner-Issue mode refuses absent evidence or non-owner initial and rerun actors', () => {
  issueReject(x => { delete x.sourceRepositoryMetadata.owner; }, /authenticated source owner/);
  issueReject(x => { x.sourceQualificationRun.actor.id = 5; }, /authenticated source owner/);
  issueReject(x => { x.sourceQualificationRun.triggering_actor.id = 5; }, /authenticated source owner/);
  issueReject(x => { delete x.sourceQualificationRun.triggering_actor; }, /authenticated source owner/);
  issueReject(x => { delete x.sourceQualificationWorkflow; }, /reviewed source contract/);
  issueReject(x => { delete x.sourceQualificationJobs; }, /authenticated qualification job/);
});

test('owner-Issue mode refuses changed workflow or identity verifier blobs and types', () => {
  issueReject(x => { x.sourceQualificationWorkflow.sha = 'b'.repeat(40); }, /reviewed source contract/);
  issueReject(x => { x.sourceIdentityVerifier.sha = 'b'.repeat(40); }, /reviewed source contract/);
  issueReject(x => { x.sourceQualificationWorkflow.path = 'wrong.yml'; }, /reviewed source contract/);
  issueReject(x => { x.sourceIdentityVerifier.type = 'symlink'; }, /reviewed source contract/);
});

test('owner-Issue mode refuses mismatched attempts, run IDs, head, job, and incomplete steps', () => {
  issueReject(x => { x.sourceQualificationJobs.total_count = 2; }, /authenticated qualification job/);
  issueReject(x => { x.sourceQualificationJobs.jobs.push(x.sourceQualificationJobs.jobs[0]); }, /authenticated qualification job/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].run_attempt = 2; }, /job identity/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].run_id = 222; }, /job identity/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].head_sha = 'b'.repeat(40); }, /job identity/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].name = 'preflight'; }, /job identity/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].conclusion = 'skipped'; }, /job identity/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps[0].conclusion = 'skipped'; }, /failed, skipped/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps[4].conclusion = 'failure'; }, /failed, skipped/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps.splice(5,1); }, /missing or reordered/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps[1].name = x.sourceQualificationJobs.jobs[0].steps[0].name; }, /duplicate/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps[1].number = 1; }, /unordered/);
  issueReject(x => { x.sourceQualificationJobs.jobs[0].steps[0].name = 'unrelated'; }, /missing or reordered/);
});

test('manual mode remains compatible and refuses mixed owner-Issue evidence', () => {
  issueReject(x => { x.sourceQualificationRun.event = 'workflow_dispatch'; }, /Unexpected owner-Issue evidence/);
  const args = ['--source-sha',SHA,'--source-run-id','12345','--package-version','4.35.0',
    '--repository-json','repo.json','--main-json','main.json','--run-json','run.json'];
  assert.throws(() => parseAdmissionPreviewArgs([...args, '--jobs-json','jobs.json']), /Complete owner-Issue/);
  assert.equal(parseAdmissionPreviewArgs([...args,'--jobs-json','jobs.json',
    '--workflow-json','workflow.json','--identity-json','identity.json'])['--jobs-json'], 'jobs.json');
});
