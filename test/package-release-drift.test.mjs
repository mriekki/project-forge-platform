import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  inspectPackageReleaseDrift,
  packagePayloadChanges,
  packagePayloadEntries,
  parseArgs
} from '../scripts/check-package-release-drift.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function git(root, args) {
  return execFileSync('git', ['-C', root, ...args], {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  }).trim();
}

function commitAll(root, message) {
  git(root, ['add', '.']);
  git(root, ['commit', '-m', message]);
  return git(root, ['rev-parse', 'HEAD']);
}

test('package payload matching includes npm-shipped Platform paths but excludes repository-only paths', () => {
  const entries = packagePayloadEntries({ files: ['bin/', 'src/', 'assets/', 'README.md'] });
  assert.deepEqual(
    packagePayloadChanges(
      ['.github/workflows/ci.yml', 'README.md', 'src/cli.mjs', 'test/cli.test.mjs', 'assets/components.json'],
      entries
    ),
    ['README.md', 'assets/components.json', 'src/cli.mjs']
  );
  assert.ok(entries.includes('package.json'));
});

test('package drift check ignores repository-only changes and detects later shipped Platform changes', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-release-drift-'));
  try {
    git(temp, ['init', '--quiet']);
    git(temp, ['config', 'user.name', 'Project Forge Test']);
    git(temp, ['config', 'user.email', 'project-forge-test@example.invalid']);

    fs.mkdirSync(path.join(temp, 'src'), { recursive: true });
    fs.mkdirSync(path.join(temp, 'test'), { recursive: true });
    fs.writeFileSync(
      path.join(temp, 'package.json'),
      JSON.stringify({
        name: '@mriekki/project-forge',
        version: '4.8.0',
        files: ['src/', 'README.md']
      }, null, 2) + '\n'
    );
    fs.writeFileSync(path.join(temp, 'README.md'), '# Project Forge\n');
    fs.writeFileSync(path.join(temp, 'src', 'cli.mjs'), 'export const value = 1;\n');
    fs.writeFileSync(path.join(temp, 'test', 'cli.test.mjs'), 'baseline\n');
    const baseline = commitAll(temp, 'baseline package');

    fs.writeFileSync(path.join(temp, 'test', 'cli.test.mjs'), 'repository-only change\n');
    commitAll(temp, 'test-only change');
    const repositoryOnly = inspectPackageReleaseDrift({ baseline }, temp);
    assert.equal(repositoryOnly.releaseNeeded, false);
    assert.deepEqual(repositoryOnly.payloadChanges, []);

    fs.writeFileSync(path.join(temp, 'src', 'cli.mjs'), 'export const value = 2;\n');
    commitAll(temp, 'consumer-visible correction');
    const shippedChange = inspectPackageReleaseDrift({ baseline }, temp);
    assert.equal(shippedChange.releaseNeeded, true);
    assert.deepEqual(shippedChange.payloadChanges, ['src/cli.mjs']);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('package drift check requires an exact published source SHA', () => {
  const sha = 'a'.repeat(40);
  assert.deepEqual(parseArgs(['--baseline', sha, '--json']), { baseline: sha, json: true });
  assert.throws(() => parseArgs(['--baseline', 'main']), /exact 40-character lowercase commit SHA/);
  assert.throws(() => parseArgs([]), /exact 40-character lowercase commit SHA/);
});

test('release skill cannot equate unchanged component revisions with no package release', () => {
  const skill = fs.readFileSync(path.join(ROOT, '.github', 'skills', 'release-project-forge', 'SKILL.md'), 'utf8');
  assert.match(skill, /exact published Platform source/i);
  assert.match(skill, /check-package-release-drift\.mjs/);
  assert.match(skill, /release\/receipts\/<version>\.json/);
  assert.match(skill, /release-receipt\.mjs/);
  assert.match(skill, /Historical Actions runs are supporting evidence, not the durable release ledger/i);
  assert.match(skill, /changed.*component revision must have live green post-merge CI/i);
  assert.match(skill, /Never conclude that no release is warranted solely because Core and Deployment revisions are unchanged/i);
  assert.match(skill, /dirty or non-`origin\/main` local component checkout may block deterministic release preparation/i);
  assert.match(skill, /must not erase or downgrade evidence that a release is needed/i);
  assert.match(skill, /NO PACKAGE RELEASE NEEDED/);
  assert.match(skill, /PACKAGE RELEASE PREPARATION BLOCKED/);
});
