import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { npmPackArgs, parseArgs, resolveNpmInvocation } from '../scripts/prepare-release.mjs';
import {
  assertVersionIncrease,
  originMatchesRepositories,
  parseArgs as parseUpdateArgs,
  parseSemver
} from '../scripts/prepare-package-update.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function runNpm(args, cwd) {
  const invocation = resolveNpmInvocation(args);
  return execFileSync(invocation.command, invocation.args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  });
}

test('release preparation requires both canonical source roots', () => {
  assert.deepEqual(parseArgs(['--core-root', 'core', '--deployment-root', 'deployment']), { core: 'core', deployment: 'deployment' });
  assert.throws(() => parseArgs(['--core-root', 'core']), /--core-root and --deployment-root are required/);
  assert.throws(() => parseArgs(['--deployment-root', 'deployment']), /--core-root and --deployment-root are required/);
});

test('release preparation accepts an explicit artifact output root', () => {
  assert.deepEqual(parseArgs(['--core-root', 'core', '--deployment-root', 'deployment', '--output', 'dist/custom']), {
    core: 'core', deployment: 'deployment', output: 'dist/custom'
  });
});

test('release preparation runs npm through Node on Windows', () => {
  const invocation = resolveNpmInvocation(['pack', '--json'], {
    platform: 'win32', execPath: 'C:\\Program Files\\nodejs\\node.exe', existsSync: () => true
  });
  assert.equal(invocation.command, 'C:\\Program Files\\nodejs\\node.exe');
  assert.deepEqual(invocation.args, ['C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npm-cli.js', 'pack', '--json']);
});

test('release npm pack disables lifecycle scripts after explicit asset verification', () => {
  assert.deepEqual(npmPackArgs('dist/pack'), ['pack', '--json', '--ignore-scripts', '--pack-destination', 'dist/pack']);
});

test('packed CLI resolves through npm exec from a neutral directory', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-npm-bin-test-'));
  try {
    const packDir = path.join(temp, 'pack');
    fs.mkdirSync(packDir);
    const packed = JSON.parse(runNpm(npmPackArgs(packDir), ROOT));
    assert.equal(packed.length, 1);
    const tarball = path.join(packDir, packed[0].filename);
    const consumer = path.join(temp, 'consumer');
    fs.mkdirSync(consumer);
    fs.writeFileSync(path.join(consumer, 'package.json'), JSON.stringify({ private: true }) + '\n');
    runNpm(['install', '--ignore-scripts', '--no-audit', '--no-fund', tarball], consumer);
    const actual = runNpm(['exec', '--', 'project-forge', 'version'], consumer).trim();
    const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
    assert.equal(actual, `${pkg.name} ${pkg.version}`);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

test('trusted publish workflow is exact-source, private-source-mapped OIDC publication with verification', () => {
  const workflow = fs.readFileSync(path.join(ROOT, '.github', 'workflows', 'npm-publish.yml'), 'utf8');
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /source_commit:/);
  assert.match(workflow, /version:/);
  assert.match(workflow, /id-token:\s*write/);
  assert.match(workflow, /actions\/checkout@d23441a48e516b6c34aea4fa41551a30e30af803/);
  assert.match(workflow, /secrets\.CORE_SOURCE_REPOSITORY/);
  assert.match(workflow, /secrets\.DEPLOYMENT_SOURCE_REPOSITORY/);
  assert.match(workflow, /steps\.sources\.outputs\.core/);
  assert.match(workflow, /steps\.sources\.outputs\.deployment/);
  assert.match(workflow, /::add-mask::/);
  assert.match(workflow, /data\.components\?\.\[id\]\?\.revision/);
  assert.doesNotMatch(workflow, /data\.components\.(?:core|deployment)\.commit/);
  assert.match(workflow, /actions\/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38/);
  assert.doesNotMatch(workflow, /uses:\s+actions\/(?:checkout|setup-node)@v\d+/);
  assert.match(workflow, /npm install --global npm@11\.21\.0/);
  assert.match(workflow, /prepare-release\.mjs/);
  assert.match(workflow, /npm publish .*--access public/);
  assert.match(workflow, /npm view/);
  assert.match(workflow, /DEADLINE=\$\(\(SECONDS \+ 600\)\)/);
  assert.match(workflow, /DELAY=5/);
  assert.match(workflow, /DELAY=30/);
  assert.match(workflow, /after 10 minutes/);
  assert.match(workflow, /Last npm registry query error/);
  assert.match(workflow, /npx --yes/);
  assert.doesNotMatch(workflow, /npm stage publish|npm stage approve/);
  assert.equal(fs.existsSync(path.join(ROOT, '.github', 'workflows', 'npm-stage.yml')), false);
});

test('release skill owns automatic version selection, protected source mapping, exact publish gate, and consumer handoff', () => {
  const skill = fs.readFileSync(path.join(ROOT, '.github', 'skills', 'release-project-forge', 'SKILL.md'), 'utf8');
  assert.match(skill, /name: release-project-forge/);
  assert.doesNotMatch(skill, /^argument-hint:/m);
  assert.match(skill, /Default invocation is `\/release-project-forge` with no version argument/);
  assert.match(skill, /Choose the next package version automatically/);
  assert.match(skill, /Do not require the user to choose `patch`, `minor`, or `major`/);
  assert.match(skill, /Explicit bump or exact-version arguments are optional overrides/);
  assert.match(skill, /prepare-package-update\.mjs/);
  assert.match(skill, /protected source-repository mappings/i);
  assert.match(skill, /Routine releases do not require a local npm login/);
  assert.match(skill, /do not query `npm trust list` on every routine release/i);
  assert.match(skill, /npm login --auth-type=web/);
  assert.match(skill, /EOTP/);
  assert.match(skill, /npm trust list @mriekki\/project-forge --json/);
  assert.match(skill, /\[NPM TRUST WRITE\]/);
  assert.match(skill, /mriekki\/project-forge-platform\/\.github\/workflows\/npm-publish\.yml/);
  assert.match(skill, /\[NPM PUBLISH\]/);
  assert.match(skill, /gh workflow run npm-publish\.yml/);
  assert.match(skill, /\/project-forge-update/);
  assert.doesNotMatch(skill, /^\s*npm stage (?:publish|approve)(?:\s|$)/m);
});

test('package update origin matching is retained only for the public Platform checkout', () => {
  assert.equal(originMatchesRepositories('git@github.com:mriekki/project-forge-platform.git', ['mriekki/project-forge-platform']), true);
  assert.equal(originMatchesRepositories('https://github.com/example/unrelated.git', ['mriekki/project-forge-platform']), false);
});

test('package update preparation requires an exact increasing semantic version and both component roots', () => {
  assert.deepEqual(parseSemver('4.5.0'), [4, 5, 0]);
  assert.doesNotThrow(() => assertVersionIncrease('4.4.2', '4.5.0'));
  assert.throws(() => assertVersionIncrease('4.4.2', '4.4.2'), /must increase/);
  assert.throws(() => assertVersionIncrease('4.4.2', '4.4.1'), /must increase/);
  assert.throws(() => parseSemver('4.5'), /Expected semantic version/);
  assert.deepEqual(parseUpdateArgs(['--version', '4.5.0', '--core-root', 'core', '--deployment-root', 'deployment']), {
    version: '4.5.0', coreRoot: 'core', deploymentRoot: 'deployment'
  });
  assert.throws(
    () => parseUpdateArgs(['--version', '4.5.0', '--core-root', 'core']),
    /--version, --core-root, and --deployment-root are required/
  );
});

test('package update preparation validates all canonical descriptors before metadata writes', () => {
  const script = fs.readFileSync(path.join(ROOT, 'scripts', 'prepare-package-update.mjs'), 'utf8');
  const validation = script.indexOf('const descriptorUpdates = []');
  const packageWrite = script.indexOf('writeJson(packageFile, nextPackage)');
  assert.notEqual(validation, -1);
  assert.notEqual(packageWrite, -1);
  assert(validation < packageWrite);
  assert.match(script, /Missing canonical descriptor/);
  assert.match(script, /components\.schemaVersion !== 2/);
  assert.match(script, /components\.core\.revision/);
  assert.doesNotMatch(script, /components\.core\.commit/);
});

test('release preparation uses npm directly outside Windows', () => {
  assert.deepEqual(resolveNpmInvocation(['test'], { platform: 'linux' }), { command: 'npm', args: ['test'] });
});

test('release preparation fails closed when the Windows npm CLI cannot be resolved', () => {
  assert.throws(
    () => resolveNpmInvocation(['test'], { platform: 'win32', execPath: 'C:\\Node\\node.exe', existsSync: () => false }),
    /Unable to locate npm CLI next to the Node executable/
  );
});
