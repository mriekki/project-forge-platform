import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), 'utf8');
}

test('cloud release preparation is owner-gated, exact-source, and non-publishing', () => {
  const workflow = read('.github/workflows/prepare-package-release.yml');

  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /issues:\s*\n\s*types: \[opened\]/);
  assert.match(workflow, /github\.event\.issue\.user\.login == github\.repository_owner/);
  assert.match(workflow, /\[project-forge-release\]/);

  for (const input of ['version', 'source_commit', 'core_revision', 'deployment_revision']) {
    assert.match(workflow, new RegExp(`\\b${input}:`));
  }

  assert.match(workflow, /actions\/checkout@d23441a48e516b6c34aea4fa41551a30e30af803/);
  assert.match(workflow, /actions\/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38/);
  assert.doesNotMatch(workflow, /uses:\s+actions\/(?:checkout|setup-node)@v\d+/);

  assert.match(workflow, /secrets\.CORE_SOURCE_REPOSITORY/);
  assert.match(workflow, /secrets\.DEPLOYMENT_SOURCE_REPOSITORY/);
  assert.match(workflow, /secrets\.PROJECT_FORGE_SOURCE_TOKEN/);
  assert.match(workflow, /::add-mask::/);
  assert.doesNotMatch(workflow, /mriekki\/project-forge-core/);
  assert.doesNotMatch(workflow, /mriekki\/project-forge-deployment-kit/);

  assert.match(workflow, /git rev-parse origin\/main/);
  assert.match(workflow, /Verify exact component main revisions/);
  assert.doesNotMatch(workflow, /actions\/runs\?head_sha=/);
  assert.doesNotMatch(workflow, /GH_TOKEN:\s*\$\{\{ secrets\.PROJECT_FORGE_SOURCE_TOKEN \}\}/);
  assert.match(workflow, /prepare-package-update\.mjs/);
  assert.match(workflow, /assemble-assets\.mjs/);
  assert.match(workflow, /verify-assets\.mjs/);
  assert.match(workflow, /npm test/);
  assert.match(workflow, /git diff --check/);
  assert.match(workflow, /release\/project-forge-\$\{VERSION\}/);
  assert.match(workflow, /git push origin/);

  assert.doesNotMatch(workflow, /npm publish/);
  assert.doesNotMatch(workflow, /gh pr create/);
});

test('release skill supports equivalent cloud and local preparation modes', () => {
  const skill = read('.github/skills/release-project-forge/SKILL.md');

  assert.match(skill, /\*\*Cloud preparation\*\*/);
  assert.match(skill, /\*\*Local preparation\*\*/);
  assert.match(skill, /prepare-package-release\.yml/);
  assert.match(skill, /\[project-forge-release\] <version>/);
  assert.match(skill, /local checkout dirtiness must not block cloud preparation/i);
  assert.match(skill, /same merge and npm publication gates/i);
  assert.match(skill, /does \*\*not\*\* authorize npm publication/);
  assert.match(skill, /cloud agent's GitHub connection is the CI-evidence authority/i);
  assert.match(skill, /least-privilege private-source checkout credential/i);
  assert.match(skill, /Do not create or dispatch a cloud preparation request until those CI checks are complete and green/i);
});

test('release process documents both preparation modes without weakening publication gates', () => {
  const process = read('docs/RELEASE_PROCESS.md');

  assert.match(process, /## Two first-class preparation modes/);
  assert.match(process, /### Cloud preparation/);
  assert.match(process, /### Local preparation/);
  assert.match(process, /prepare-package-release\.yml/);
  assert.match(process, /ONE PACKAGE PR MERGE GATE/);
  assert.match(process, /ONE EXACT NPM PUBLISH GATE/);
  assert.match(process, /Dirty or stale local component checkouts block only local preparation/);
  assert.match(process, /cloud agent.*green post-merge CI/i);
  assert.match(process, /does not need private Actions API access/i);
});
