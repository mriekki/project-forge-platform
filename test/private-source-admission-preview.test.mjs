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
