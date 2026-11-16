import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { componentRevisionForDisplay, run } from '../src/cli.mjs';
import { applyProfile, planProfile } from '../src/engine.mjs';

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
  for (const command of ['install', 'update', 'enable', 'repair', 'status', 'check', 'version']) {
    for (const flag of ['--help', '-h']) {
      const result = runCli([command, flag]);
      assert.equal(result.status, 0, `${command} ${flag}: ${result.stderr}`);
      assert.equal(result.stderr, '');
      assert.match(result.stdout, new RegExp(`Usage:\\s+project-forge ${command}`));
    }
  }
});

function feedbackPackageFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-feedback-cli-'));
  const packageRoot = path.join(root, 'package');
  const targetRoot = path.join(root, 'consumer');
  fs.mkdirSync(packageRoot, { recursive: true });
  fs.mkdirSync(targetRoot, { recursive: true });
  const components = {
    core: { revision: 'a'.repeat(40), version: '4.3.1', distribution: 'greenfield-workspace' },
    deployment: { revision: 'b'.repeat(40), distribution: 'greenfield-project' },
    authentication: { revision: 'c'.repeat(40), distribution: 'greenfield-project' },
    feedback: { revision: 'd'.repeat(40), distribution: 'greenfield-project' }
  };
  for (const [id, component] of Object.entries(components)) {
    const sourceRoot = `assets/generated/${id}`;
    const descriptor = `assets/${id}/distribution.json`;
    const source = `${id}.txt`;
    fs.mkdirSync(path.join(packageRoot, sourceRoot), { recursive: true });
    fs.mkdirSync(path.join(packageRoot, `assets/${id}`), { recursive: true });
    fs.writeFileSync(path.join(packageRoot, sourceRoot, source), `${id} source\n`);
    fs.writeFileSync(path.join(packageRoot, descriptor), JSON.stringify({
      mappings: [{ source, destination: `tools/${id}.txt` }]
    }));
    Object.assign(component, { descriptor, sourceRoot });
  }
  const standard = { components: ['core', 'deployment'] };
  const household = { components: ['core', 'deployment', 'authentication'] };
  const packageData = {
    root: packageRoot,
    pkg: { name: '@mriekki/project-forge', version: '4.28.0' },
    assets: {
      defaultProfile: 'greenfield-project',
      profiles: {
        'greenfield-project': standard,
        'greenfield-household-project': household,
        'greenfield-feedback-project': { components: ['core', 'deployment', 'feedback'] },
        'greenfield-household-feedback-project': {
          components: ['core', 'deployment', 'authentication', 'feedback']
        }
      },
      components
    }
  };
  return { root, targetRoot, packageData };
}

test('CLI explicitly enables Feedback without changing an existing household Auth selection', async () => {
  const fixture = feedbackPackageFixture();
  try {
    const initial = planProfile(fixture.packageData, 'greenfield-household-project', fixture.targetRoot);
    applyProfile(fixture.packageData, initial, fixture.targetRoot, 'consumer', 'approved-baseline');
    const beforeAuth = fs.readFileSync(path.join(fixture.targetRoot, 'tools/authentication.txt'));

    const status = await run(['enable', 'feedback', '--root', fixture.targetRoot, '--apply'], fixture.packageData);
    assert.equal(status, 0);
    const umbrella = JSON.parse(fs.readFileSync(path.join(fixture.targetRoot, 'PROJECT_FORGE_BASELINE.json'), 'utf8'));
    assert.equal(umbrella.profile, 'greenfield-household-feedback-project');
    assert.deepEqual(Object.keys(umbrella.components).sort(), ['authentication', 'core', 'deployment', 'feedback']);
    assert.deepEqual(fs.readFileSync(path.join(fixture.targetRoot, 'tools/authentication.txt')), beforeAuth);
    assert.equal(fs.readFileSync(path.join(fixture.targetRoot, 'tools/feedback.txt'), 'utf8'), 'feedback source\n');
    assert.equal(umbrella.consumer, 'consumer');
    assert.equal(umbrella.consumerBaseline, 'approved-baseline');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('CLI Feedback opt-in refuses existing managed drift without writing the capability', async () => {
  const fixture = feedbackPackageFixture();
  try {
    const initial = planProfile(fixture.packageData, 'greenfield-project', fixture.targetRoot);
    applyProfile(fixture.packageData, initial, fixture.targetRoot, 'consumer', 'approved-baseline');
    fs.writeFileSync(path.join(fixture.targetRoot, 'tools/core.txt'), 'local edit\n');

    const status = await run(['enable', 'feedback', '--root', fixture.targetRoot, '--apply'], fixture.packageData);
    assert.equal(status, 2);
    assert.equal(fs.existsSync(path.join(fixture.targetRoot, 'tools/feedback.txt')), false);
    const umbrella = JSON.parse(fs.readFileSync(path.join(fixture.targetRoot, 'PROJECT_FORGE_BASELINE.json'), 'utf8'));
    assert.equal(umbrella.profile, 'greenfield-project');
    assert.equal(Object.hasOwn(umbrella.components, 'feedback'), false);
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('CLI still rejects unknown options', () => {
  const result = runCli(['update', '--definitely-not-an-option']);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /Project Forge error: Unknown option: --definitely-not-an-option/);
});

test('CLI repair rejects a repository with no installed umbrella baseline', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-cli-repair-'));
  try {
    const result = runCli(['repair', '--root', temp, '--apply']);
    assert.equal(result.status, 2);
    assert.match(result.stderr, /No Project Forge baseline; install first/);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
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
