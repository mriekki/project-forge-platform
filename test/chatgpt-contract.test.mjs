import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const predecessorUpper = ['P', 'OC'].join('');
const predecessorLower = predecessorUpper.toLowerCase();
const requiredDocuments = [
  'ADMIN.md',
  'EXISTING_PROJECT.md',
  'NEW_PROJECT.md',
  'ONBOARDING.md',
  'PROJECT_INSTRUCTIONS.md',
  'PROJECT_RULES.md',
  'USER_PROFILE.schema.json',
];

async function text(relative) {
  return readFile(path.join(root, relative), 'utf8');
}

function canonicalGitBlob(relative) {
  const result = spawnSync('git', ['show', `HEAD:${relative}`], {
    cwd: root,
    encoding: null,
    maxBuffer: 1024 * 1024,
  });
  assert.equal(result.status, 0, `Unable to read canonical Git blob ${relative}: ${result.stderr?.toString() ?? ''}`);
  return result.stdout;
}

async function descriptor() {
  return JSON.parse(await text('chatgpt/current.json'));
}

function contractPath(value, name) {
  return `${value.snapshotPath}/${name}`;
}

test('public ChatGPT descriptor resolves immutable Project Forge contract v15', async () => {
  const value = await descriptor();
  assert.equal(value.schemaVersion, 1);
  assert.equal(value.channel, 'stable');
  assert.equal(value.contractVersion, 15);
  assert.equal(value.snapshotPath, 'chatgpt/contracts/v15');
  assert.deepEqual(value.documents.map((item) => path.basename(item.path)), requiredDocuments);

  const actual = {};
  const declared = {};
  const seen = new Set();
  for (const document of value.documents) {
    assert.ok(document.path.startsWith(`${value.snapshotPath}/`));
    assert.match(document.sha256, /^[0-9a-f]{64}$/);
    assert.equal(seen.has(document.path), false, `duplicate document ${document.path}`);
    seen.add(document.path);
    actual[document.path] = createHash('sha256').update(canonicalGitBlob(document.path)).digest('hex');
    declared[document.path] = document.sha256;
  }
  assert.deepEqual(declared, actual, 'descriptor hashes must match immutable v15 document bytes');
});

test('descriptor keeps private foundational source topology out of the public contract', async () => {
  const value = await descriptor();
  assert.equal(Object.hasOwn(value, 'sourceProvenance'), false);
  assert.equal(Object.hasOwn(value.generation.bootstrap, 'repository'), false);
  assert.equal(Object.hasOwn(value.generation.bootstrap, 'commit'), false);
  assert.match(value.generation.bootstrap.revision, /^[0-9a-f]{40}$/);
  assert.equal(value.generation.bootstrap.revision, '05d5f7144cc78b78a087a9ed95c334eae6fa90e9');
  assert.equal(value.generation.bootstrap.protocolVersion, 12);
  assert.equal(value.generation.bootstrap.catalogVersion, 13);
});

test('generation aligns the published package with the accepted Bootstrap revision', async () => {
  const value = await descriptor();
  assert.equal(value.generation.manifestFilename, 'PROJECT_BOOTSTRAP.json');
  assert.equal(value.generation.bootstrap.revision, '05d5f7144cc78b78a087a9ed95c334eae6fa90e9');
  assert.equal(value.generation.bootstrap.protocolVersion, 12);
  assert.equal(value.generation.bootstrap.catalogVersion, 13);
  assert.equal(value.generation.bootstrap.portableRequirements.bootstrapRevision, value.generation.bootstrap.revision);
  assert.equal(value.generation.package, '@mriekki/project-forge');
  assert.equal(value.generation.packageVersion, '4.13.4');
  assert.equal(value.generation.profile, 'greenfield-project');
  assert.equal(value.generation.bootstrapProtocolVersion, 12);
  assert.equal(value.bootstrapUrl, 'https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json');
});

test('stable generation contract preserves a privacy-safe Bootstrap pin boundary', async () => {
  const value = await descriptor();
  const newProject = await text(contractPath(value, 'NEW_PROJECT.md'));

  assert.match(newProject, /generation\.bootstrap\.revision/);
  assert.match(newProject, /protected configuration/);
  assert.match(newProject, /does not expose the private foundational repository/);
  assert.doesNotMatch(newProject, /sourceProvenance/);
  assert.doesNotMatch(newProject, /generation\.bootstrap\.commit/);
});

test('active Project Forge contract uses current public identifiers without private topology', async () => {
  const value = await descriptor();
  const active = await Promise.all([
    'ADMIN.md',
    'EXISTING_PROJECT.md',
    'NEW_PROJECT.md',
    'ONBOARDING.md',
    'PROJECT_INSTRUCTIONS.md',
    'PROJECT_RULES.md',
  ].map((name) => text(contractPath(value, name))));
  const joined = active.join('\n');

  for (const required of [
    'PROJECT_BOOTSTRAP.json',
    'PROJECT_INPUT.json',
    'docs/product/PROJECT_DECISION_LOG.md',
    '@mriekki/project-forge',
    '[generate-project]',
    '[invite-project-forge]',
    '/accept-project-forge',
    '/project-forge-doctor',
    'mriekki/project-forge-platform',
    'mriekki/project-forge-control-plane',
  ]) {
    assert.match(joined, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }

  for (const forbidden of [
    'mriekki/project-forge-core',
    'mriekki/project-forge-bootstrap',
    'mriekki/project-forge-deployment-kit',
    'mriekki/project-forge-adoption-kit',
    'sourceProvenance',
  ]) {
    assert.doesNotMatch(joined, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }

  for (const retired of [
    `${predecessorUpper}_BOOTSTRAP.json`,
    '@mriekki/lean',
    'lean-agentic-core',
    `lean-${predecessorLower}-bootstrap`,
    'lean-platform',
    `[generate-${predecessorLower}]`,
    '[invite-lean]',
    '/accept-lean',
    '/lean-doctor',
    'LEAN_BASELINE.json',
    'Project_INPUT.json',
  ]) {
    assert.doesNotMatch(joined, new RegExp(retired.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }

  assert.match(joined, /New Project/);
  assert.doesNotMatch(joined, /New Project: <idea>/);
  assert.doesNotMatch(joined, /New Project from:/);
});

test('public contract teaches one guided New Project prompt', async () => {
  const value = await descriptor();
  const newProject = await text(contractPath(value, 'NEW_PROJECT.md'));
  const onboarding = await text(contractPath(value, 'ONBOARDING.md'));
  const instructions = await text(contractPath(value, 'PROJECT_INSTRUCTIONS.md'));
  const rules = await text(contractPath(value, 'PROJECT_RULES.md'));
  const joined = `${newProject}\n${onboarding}\n${instructions}\n${rules}`;

  assert.match(newProject, /only user-facing ChatGPT Project-creation prompt/i);
  assert.match(newProject, /```text\r?\nNew Project\r?\n```/);
  assert.match(newProject, /Start from an idea/);
  assert.match(newProject, /Start from an existing product or source/);
  assert.match(newProject, /Not sure — recommend a path/);
  assert.match(joined, /Do not teach.*separate greenfield\/import command syntax/is);
  assert.doesNotMatch(joined, /New Project: <idea>/);
  assert.doesNotMatch(joined, /New Project from:/);
});

test('public contract makes repositories authoritative instead of legacy handoffs', async () => {
  const value = await descriptor();
  const existing = await text(contractPath(value, 'EXISTING_PROJECT.md'));
  const onboarding = await text(contractPath(value, 'ONBOARDING.md'));
  const instructions = await text(contractPath(value, 'PROJECT_INSTRUCTIONS.md'));
  const rules = await text(contractPath(value, 'PROJECT_RULES.md'));
  const joined = `${existing}\n${onboarding}\n${instructions}\n${rules}`;

  assert.match(existing, /repository is the durable handoff/i);
  assert.match(joined, /legacy\/versioned handoff/i);
  assert.match(joined, /not an onboarding dependency/i);
  assert.match(instructions, /Do not add legacy\/versioned handoff-file references/i);
  assert.match(joined, /authoritative current state/i);
});

test('public contract makes one canonical instruction plus one personal profile explicit', async () => {
  const value = await descriptor();
  const onboarding = await text(contractPath(value, 'ONBOARDING.md'));
  const instructions = await text(contractPath(value, 'PROJECT_INSTRUCTIONS.md'));
  const schema = JSON.parse(await text(contractPath(value, 'USER_PROFILE.schema.json')));

  assert.match(onboarding, /Every Builder uses the same canonical Project Forge Project instruction/);
  assert.match(onboarding, /same ChatGPT Project instructions field/);
  assert.match(onboarding, /Developer Profile is the only Builder-specific part/);
  assert.match(onboarding, /Verify my Project Forge setup\./);
  assert.match(instructions, /Use the Developer Profile in this ChatGPT Project only for identity/);

  assert.equal(schema.title, 'Project Forge Developer Profile');
  assert.equal(schema.additionalProperties, false);
  assert.deepEqual(schema.required, ['schemaVersion', 'githubOwner']);
  assert.match(schema.$id, /mriekki\/project-forge-platform\/main\/chatgpt\/contracts\/v15/);

  for (const forbidden of ['password', 'token', 'secret', `${predecessorLower}State`, 'projectState', 'workItem', 'commitSha']) {
    assert.equal(Object.hasOwn(schema.properties, forbidden), false);
  }
});

test('public contract carries current bounded-decision and work-item guidance', async () => {
  const value = await descriptor();
  const newProject = await text(contractPath(value, 'NEW_PROJECT.md'));
  const rules = await text(contractPath(value, 'PROJECT_RULES.md'));
  const joined = `${newProject}\n${rules}`;

  assert.match(joined, /\[RECOMMENDED\]/);
  assert.match(joined, /default\/preselected/i);
  assert.match(joined, /one material question at a time/i);
  assert.match(joined, /capability-sized coherent slices/i);
  assert.match(joined, /Do not split merely by screen/i);
});

test('public contract carries acknowledged Project Forge drift continuation safety', async () => {
  const value = await descriptor();
  const existing = await text(contractPath(value, 'EXISTING_PROJECT.md'));
  const rules = await text(contractPath(value, 'PROJECT_RULES.md'));
  const joined = `${existing}\n${rules}`;

  assert.match(joined, /\.project-forge\/UPSTREAM_FIX_HANDOFF\.md/);
  assert.match(joined, /Continue consumer work with acknowledged Project Forge drift/);
  assert.match(joined, /unexplained managed drift/i);
  assert.match(joined, /Keep the workaround and handoff unstaged/i);
  assert.match(joined, /does not authorize committing shared-managed paths/i);
});

test('control-plane command descriptor matches the current public contract', async () => {
  const value = await descriptor();
  assert.equal(value.controlPlane.repository, 'mriekki/project-forge-control-plane');
  assert.equal(value.controlPlane.inviteIssuePrefix, '[invite-project-forge]');
  assert.equal(value.controlPlane.revokeIssuePrefix, '[revoke-project-forge]');
  assert.equal(value.controlPlane.doctorIssuePrefix, '[project-forge-doctor]');
  assert.equal(value.controlPlane.generateIssuePrefix, '[generate-project]');
  assert.equal(value.controlPlane.acceptCommand, '/accept-project-forge');
  assert.equal(value.controlPlane.declineCommand, '/decline-project-forge');
  assert.equal(value.controlPlane.doctorCommand, '/project-forge-doctor');
});

test('active public Builder pages use current Project Forge onboarding vocabulary', async () => {
  const welcome = await text('WELCOME.md');
  const setup = await text('chatgpt/SETUP.md');
  const startHere = await text('chatgpt/START_HERE.md');
  const readme = await text('README.md');
  const joined = [welcome, setup, startHere, readme].join('\n');

  assert.match(welcome, /Build real software\. Learn the engineering behind it\./);
  assert.match(joined, /Project Forge Builder/);
  assert.match(joined, /\/accept-project-forge/);
  assert.match(joined, /\/project-forge-doctor/);
  assert.match(joined, /```text\r?\nNew Project\r?\n```/);
  assert.match(joined, /supported start mode/i);
  assert.doesNotMatch(joined, /New Project: <idea>/);
  assert.doesNotMatch(joined, /New Project from:/);
  assert.doesNotMatch(joined, new RegExp(predecessorUpper));

  for (const retired of ['accept-lean', 'lean-doctor', 'lean-platform']) {
    assert.doesNotMatch(joined, new RegExp(retired));
  }
});
