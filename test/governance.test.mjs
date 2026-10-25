import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('Platform CI exposes one stable required branch-protection gate', () => {
  const workflow = fs.readFileSync(path.join(ROOT, '.github', 'workflows', 'ci.yml'), 'utf8');
  assert.match(workflow, /pull_request:/);
  assert.match(workflow, /\r?\n  required:\r?\n    name: required\r?\n/);
  assert.match(workflow, /needs:\r?\n      - test/);
  assert.match(workflow, /needs\.test\.result/);
});

test('npm publication is bound to the protected publication environment', () => {
  const workflow = fs.readFileSync(path.join(ROOT, '.github', 'workflows', 'npm-publish.yml'), 'utf8');
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
});
