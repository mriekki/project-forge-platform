import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { applyProfile, checkProfile, planProfile } from '../src/engine.mjs';

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-exact-managed-set-'));
  const packageRoot = path.join(root, 'package');
  const consumerRoot = path.join(root, 'consumer');

  fs.mkdirSync(path.join(packageRoot, 'assets/core/source/core'), { recursive: true });
  fs.mkdirSync(path.join(packageRoot, 'assets/deployment/source/src'), { recursive: true });
  fs.mkdirSync(consumerRoot, { recursive: true });

  fs.writeFileSync(path.join(packageRoot, 'assets/core/source/core/a.txt'), 'core-v1\n');
  fs.writeFileSync(path.join(packageRoot, 'assets/deployment/source/src/b.txt'), 'kit-v1\n');
  fs.writeFileSync(
    path.join(packageRoot, 'assets/core/distribution.json'),
    JSON.stringify({
      name: 'greenfield-workspace',
      mappings: [{ source: 'core/a.txt', destination: '.github/a.txt' }]
    })
  );
  fs.writeFileSync(
    path.join(packageRoot, 'assets/deployment/distribution.json'),
    JSON.stringify({
      name: 'greenfield-project',
      schemaVersion: 1,
      mappings: [{ source: 'src/b.txt', destination: 'tools/b.txt' }]
    })
  );

  const packageData = {
    root: packageRoot,
    pkg: { name: '@mriekki/project-forge', version: '0.1.0' },
    assets: {
      schemaVersion: 2,
      defaultProfile: 'greenfield-project',
      profiles: { 'greenfield-project': { components: ['core', 'deployment'] } },
      components: {
        core: {
          revision: 'a'.repeat(40),
          version: '1.0.0',
          distribution: 'greenfield-workspace',
          descriptor: 'assets/core/distribution.json',
          sourceRoot: 'assets/core/source'
        },
        deployment: {
          revision: 'b'.repeat(40),
          distribution: 'greenfield-project',
          descriptor: 'assets/deployment/distribution.json',
          sourceRoot: 'assets/deployment/source'
        }
      }
    }
  };

  return { packageRoot, consumerRoot, packageData };
}

test('successful update converges to the exact managed set and preserves unmanaged consumer files', () => {
  const { packageRoot, consumerRoot, packageData } = fixture();

  applyProfile(
    packageData,
    planProfile(packageData, 'greenfield-project', consumerRoot),
    consumerRoot,
    'demo-project',
    '@mriekki/project-forge@0.1.0'
  );

  const unmanaged = path.join(consumerRoot, 'notes/local.txt');
  fs.mkdirSync(path.dirname(unmanaged), { recursive: true });
  fs.writeFileSync(unmanaged, 'consumer-owned\n');

  fs.writeFileSync(path.join(packageRoot, 'assets/deployment/source/src/c.txt'), 'kit-v2\n');
  fs.writeFileSync(
    path.join(packageRoot, 'assets/deployment/distribution.json'),
    JSON.stringify({
      name: 'greenfield-project',
      schemaVersion: 1,
      mappings: [{ source: 'src/c.txt', destination: 'tools/c.txt' }]
    })
  );
  packageData.pkg.version = '0.2.0';
  packageData.assets.components.deployment.revision = 'c'.repeat(40);

  const plan = planProfile(packageData, 'greenfield-project', consumerRoot);
  const deployment = plan.plans.find((item) => item.componentId === 'deployment');
  assert.deepEqual(deployment.retired.map((item) => [item.path, item.state]), [['tools/b.txt', 'REMOVE']]);
  assert.equal(plan.unsafe.length, 0);

  applyProfile(
    packageData,
    plan,
    consumerRoot,
    'demo-project',
    '@mriekki/project-forge@0.2.0'
  );

  assert.equal(fs.existsSync(path.join(consumerRoot, 'tools/b.txt')), false);
  assert.equal(fs.readFileSync(path.join(consumerRoot, 'tools/c.txt'), 'utf8'), 'kit-v2\n');
  assert.equal(fs.readFileSync(unmanaged, 'utf8'), 'consumer-owned\n');

  const baseline = JSON.parse(fs.readFileSync(path.join(consumerRoot, 'DEPLOYMENT_BASELINE.json')));
  assert.deepEqual(baseline.managedPaths.map((item) => item.path), ['tools/c.txt']);
  assert.equal(checkProfile(packageData, 'greenfield-project', consumerRoot).clean, true);
});
