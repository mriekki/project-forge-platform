import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WORKFLOWS = path.join(ROOT, '.github', 'workflows');

test('Platform CI exposes one stable required branch-protection gate', () => {
  const workflow = fs.readFileSync(path.join(WORKFLOWS, 'ci.yml'), 'utf8');
  assert.match(workflow, /pull_request:/);
  assert.match(workflow, /\r?\n  required:\r?\n    name: required\r?\n/);
  assert.match(workflow, /needs:\r?\n      - test/);
  assert.match(workflow, /needs\.test\.result/);
});

test('Platform CI tests every supported Node line on Windows and Ubuntu', () => {
  const workflow = fs.readFileSync(path.join(WORKFLOWS, 'ci.yml'), 'utf8');
  assert.match(workflow, /- ubuntu-latest/);
  assert.match(workflow, /- windows-latest/);
  for (const version of ['20', '22', '24']) {
    assert.match(workflow, new RegExp(`- '${version}'`));
  }
  assert.match(workflow, /node-version: \$\{\{ matrix\.node \}\}/);
});

test('all external Platform workflow actions are pinned by immutable commit SHA', () => {
  for (const entry of fs.readdirSync(WORKFLOWS, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith('.yml')) continue;
    const workflow = fs.readFileSync(path.join(WORKFLOWS, entry.name), 'utf8');
    for (const match of workflow.matchAll(/^\s*-?\s*uses:\s*([^\s#]+)/gm)) {
      const uses = match[1];
      if (uses.startsWith('./')) continue;
      assert.match(
        uses,
        /^[^@\s]+@[0-9a-f]{40}$/,
        `${entry.name} must pin external action ${uses} by exact commit SHA`,
      );
    }
  }
});

test('stable platform health continuously verifies live contract and exact stable package', () => {
  const workflow = fs.readFileSync(path.join(WORKFLOWS, 'stable-platform-health.yml'), 'utf8');
  assert.match(workflow, /schedule:/);
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /scripts\/check-chatgpt-contract-alignment\.mjs/);
  assert.match(workflow, /node --input-type=module <<'NODE'/);
  assert.match(workflow, /import \{ createHash \} from 'node:crypto';/);
  assert.match(workflow, /import \{ readFileSync \} from 'node:fs';/);
  assert.doesNotMatch(workflow, /const crypto = require\('node:crypto'\)/);
  assert.match(workflow, /Live immutable contract hash mismatch/);
  assert.match(workflow, /invitationPolicyUrl/);
  assert.match(workflow, /npm view "\$\{PACKAGE\}@\$\{VERSION\}" version/);
  assert.match(workflow, /npx --yes "\$\{PACKAGE\}@\$\{VERSION\}" version/);
  assert.match(workflow, /\[project-forge-health\] Stable platform audit failing/);
  assert.doesNotMatch(workflow, /@latest/);
});

test('npm publication is bound to the protected publication environment', () => {
  const workflow = fs.readFileSync(path.join(WORKFLOWS, 'npm-publish.yml'), 'utf8');
  assert.match(workflow, /\r?\n  publish:\r?\n    environment: npm-production\r?\n/);
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /source_commit:/);
  assert.match(workflow, /version:/);
  assert.match(workflow, /id-token:\s*write/);
  assert.match(workflow, /npm publish .*--access public/);
});

test('Platform governance documentation keeps admin controls narrow', () => {
  const doc = fs.readFileSync(path.join(ROOT, 'docs', 'GITHUB_GOVERNANCE.md'), 'utf8');
  assert.match(doc, /CI \/ required/);
  assert.match(doc, /npm-production/);
  assert.match(doc, /required human reviewer/i);
  assert.match(doc, /use no bypass actor by default/i);
  assert.match(doc, /does not authorize merge, Project generation, consumer updates/i);
  assert.match(doc, /Stable Platform Health/);
});
