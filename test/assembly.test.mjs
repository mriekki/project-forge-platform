import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { assembleAssets } from '../scripts/assemble-assets.mjs';
import { verifyAssets } from '../scripts/verify-assets.mjs';
import { loadPackageData } from '../src/package-data.mjs';

function gitRepo(root) {
  execFileSync('git', ['init', '-q', root]);
  execFileSync('git', ['-C', root, 'config', 'user.email', 'test@example.com']);
  execFileSync('git', ['-C', root, 'config', 'user.name', 'Test']);
  execFileSync('git', ['-C', root, 'add', '.']);
  execFileSync('git', ['-C', root, 'commit', '-qm', 'fixture']);
  return execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
}

function fixturePackage(temp, coreDescriptor, deploymentDescriptor, coreVersion = '9.9.9') {
  const packageRoot = path.join(temp, 'package');
  const coreRoot = path.join(temp, 'core');
  const deploymentRoot = path.join(temp, 'deployment');
  for (const dir of [path.join(packageRoot, 'assets/core'), path.join(packageRoot, 'assets/deployment'), path.join(coreRoot, 'distributions'), path.join(coreRoot, 'core'), path.join(deploymentRoot, 'distributions'), path.join(deploymentRoot, 'src')]) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(coreRoot, 'distributions/greenfield-workspace.json'), JSON.stringify(coreDescriptor));
  fs.writeFileSync(path.join(coreRoot, 'core/a.txt'), 'core\n');
  fs.writeFileSync(path.join(coreRoot, 'COMPATIBILITY.json'), JSON.stringify({ projectForgeCoreVersion: coreVersion }));
  fs.writeFileSync(path.join(deploymentRoot, 'distributions/greenfield-project.json'), JSON.stringify(deploymentDescriptor));
  fs.writeFileSync(path.join(deploymentRoot, 'src/b.txt'), 'deployment\n');
  const coreRevision = gitRepo(coreRoot);
  const deploymentRevision = gitRepo(deploymentRoot);
  fs.writeFileSync(path.join(packageRoot, 'package.json'), JSON.stringify({ name: '@mriekki/project-forge', version: '0.1.0' }));
  fs.writeFileSync(path.join(packageRoot, 'assets/core/distribution.json'), JSON.stringify(coreDescriptor));
  fs.writeFileSync(path.join(packageRoot, 'assets/deployment/distribution.json'), JSON.stringify(deploymentDescriptor));
  fs.writeFileSync(path.join(packageRoot, 'assets/components.json'), JSON.stringify({
    schemaVersion: 2,
    package: '@mriekki/project-forge', version: '0.1.0', defaultProfile: 'greenfield-project', profiles: { 'greenfield-project': { components: ['core', 'deployment'] } },
    components: {
      core: { revision: coreRevision, version: coreVersion, distribution: 'greenfield-workspace', descriptor: 'assets/core/distribution.json', canonicalDescriptor: 'distributions/greenfield-workspace.json', sourceRoot: 'assets/generated/core' },
      deployment: { revision: deploymentRevision, distribution: 'greenfield-project', descriptor: 'assets/deployment/distribution.json', canonicalDescriptor: 'distributions/greenfield-project.json', sourceRoot: 'assets/generated/deployment' }
    }
  }));
  return { packageRoot, coreRoot, deploymentRoot, packageData: loadPackageData(packageRoot) };
}

test('assembly verifies exact revisions/descriptors and creates a self-contained privacy-safe payload', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-assembly-'));
  const coreDescriptor = { name: 'greenfield-workspace', mappings: [{ source: 'core/a.txt', destination: '.github/a.txt' }] };
  const deploymentDescriptor = { name: 'greenfield-project', schemaVersion: 1, mappings: [{ source: 'src/b.txt', destination: 'tools/b.txt' }] };
  const { packageRoot, coreRoot, deploymentRoot, packageData } = fixturePackage(temp, coreDescriptor, deploymentDescriptor);
  const result = assembleAssets(packageData, { core: coreRoot, deployment: deploymentRoot });
  assert.equal(result.schemaVersion, 2);
  assert.equal(result.components.core.files.length, 1);
  assert.equal(result.components.deployment.files.length, 1);
  assert.equal(result.components.core.revision, packageData.assets.components.core.revision);
  assert.equal(Object.hasOwn(result.components.core, 'repository'), false);
  assert.equal(Object.hasOwn(result.components.core, 'commit'), false);
  assert.equal(fs.readFileSync(path.join(packageRoot, 'assets/generated/core/core/a.txt'), 'utf8'), 'core\n');
  assert.equal(verifyAssets(packageData), 2);
});

test('assembly reads canonical Git blob bytes from a clean CRLF checkout', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-assembly-crlf-'));
  const coreDescriptor = { name: 'greenfield-workspace', mappings: [{ source: 'core/a.txt', destination: '.github/a.txt' }] };
  const deploymentDescriptor = { name: 'greenfield-project', schemaVersion: 1, mappings: [{ source: 'src/b.txt', destination: 'tools/b.txt' }] };
  const { packageRoot, coreRoot, deploymentRoot, packageData } = fixturePackage(temp, coreDescriptor, deploymentDescriptor);

  execFileSync('git', ['-C', deploymentRoot, 'config', 'core.autocrlf', 'true']);
  fs.rmSync(path.join(deploymentRoot, 'src/b.txt'));
  execFileSync('git', ['-C', deploymentRoot, 'checkout', '--', 'src/b.txt']);

  assert.equal(fs.readFileSync(path.join(deploymentRoot, 'src/b.txt'), 'utf8'), 'deployment\r\n');
  assert.equal(execFileSync('git', ['-C', deploymentRoot, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' }).trim(), '');

  assembleAssets(packageData, { core: coreRoot, deployment: deploymentRoot });
  assert.equal(fs.readFileSync(path.join(packageRoot, 'assets/generated/deployment/src/b.txt'), 'utf8'), 'deployment\n');
});

test('assembly rejects a source descriptor that differs from the package contract', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-assembly-reject-'));
  const canonicalCore = { name: 'greenfield-workspace', mappings: [{ source: 'core/a.txt', destination: '.github/DIFFERENT.txt' }] };
  const packagedCore = { name: 'greenfield-workspace', mappings: [{ source: 'core/a.txt', destination: '.github/a.txt' }] };
  const deploymentDescriptor = { name: 'greenfield-project', schemaVersion: 1, mappings: [{ source: 'src/b.txt', destination: 'tools/b.txt' }] };
  const { packageRoot, coreRoot, deploymentRoot } = fixturePackage(temp, canonicalCore, deploymentDescriptor, '1.0.0');
  fs.writeFileSync(path.join(packageRoot, 'assets/core/distribution.json'), JSON.stringify(packagedCore));
  const packageData = loadPackageData(packageRoot);
  assert.throws(() => assembleAssets(packageData, { core: coreRoot, deployment: deploymentRoot }), /descriptor does not match/);
});

test('assembly rejects tracked changes in an exact canonical checkout', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-assembly-dirty-'));
  const coreDescriptor = { name: 'greenfield-workspace', mappings: [{ source: 'core/a.txt', destination: '.github/a.txt' }] };
  const deploymentDescriptor = { name: 'greenfield-project', schemaVersion: 1, mappings: [{ source: 'src/b.txt', destination: 'tools/b.txt' }] };
  const { coreRoot, deploymentRoot, packageData } = fixturePackage(temp, coreDescriptor, deploymentDescriptor);
  fs.writeFileSync(path.join(coreRoot, 'core/a.txt'), 'locally modified\n');
  assert.throws(() => assembleAssets(packageData, { core: coreRoot, deployment: deploymentRoot }), /tracked working-tree changes/);
});
