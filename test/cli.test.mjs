import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { componentRevisionForDisplay } from '../src/cli.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CLI = path.join(ROOT, 'bin', 'project-forge.mjs');

function runCli(args) {
  return spawnSync(process.execPath, [CLI, ...args], {
    cwd: ROOT,
    encoding: 'utf8'
  });
}

test('CLI accepts global help flags', () => {
  for (const args of [['--help'], ['-h']]) {
    const result = runCli(args);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stderr, '');
    assert.match(result.stdout, /Commands:/);
    assert.match(result.stdout, /-h, --help/);
  }
});

test('CLI accepts command help flags without requiring repository state', () => {
  for (const command of ['install', 'update', 'status', 'check', 'version']) {
    for (const flag of ['--help', '-h']) {
      const result = runCli([command, flag]);
      assert.equal(result.status, 0, `${command} ${flag}: ${result.stderr}`);
      assert.equal(result.stderr, '');
      assert.match(result.stdout, new RegExp(`Usage:\\s+project-forge ${command}`));
    }
  }
});

test('CLI still rejects unknown options', () => {
  const result = runCli(['update', '--definitely-not-an-option']);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /Project Forge error: Unknown option: --definitely-not-an-option/);
});

test('CLI component revision display prefers schema v2 revision with legacy fallback', () => {
  assert.equal(componentRevisionForDisplay({ revision: 'a'.repeat(40) }), 'a'.repeat(40));
  assert.equal(componentRevisionForDisplay({ commit: 'b'.repeat(40) }), 'b'.repeat(40));
  assert.equal(componentRevisionForDisplay({}), '<unknown revision>');
});

test('CLI status reports schema v2 component revisions instead of undefined', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-cli-status-'));
  try {
    const coreRevision = 'a'.repeat(40);
    const deploymentRevision = 'b'.repeat(40);
    fs.writeFileSync(path.join(temp, 'PROJECT_FORGE_BASELINE.json'), JSON.stringify({
      schemaVersion: 2,
      package: '@mriekki/project-forge',
      version: '4.8.0',
      profile: 'greenfield-project',
      consumer: 'fixture',
      consumerBaseline: '@mriekki/project-forge@4.8.0',
      components: {
        core: {
          revision: coreRevision,
          version: '4.0.0',
          distribution: 'greenfield-workspace'
        },
        deployment: {
          revision: deploymentRevision,
          distribution: 'greenfield-project'
        }
      }
    }, null, 2) + '\n');

    const result = runCli(['status', '--root', temp]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stderr, '');
    assert.match(result.stdout, new RegExp(`core: 4\\.0\\.0 @ ${coreRevision}`));
    assert.match(result.stdout, new RegExp(`deployment: ${deploymentRevision}`));
    assert.doesNotMatch(result.stdout, /undefined/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
