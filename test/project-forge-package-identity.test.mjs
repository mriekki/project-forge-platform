import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');

function readJson(relative) {
  return JSON.parse(fs.readFileSync(path.join(root, relative), 'utf8'));
}

function walk(relative) {
  const absolute = path.join(root, relative);
  if (!fs.existsSync(absolute)) return [];
  if (fs.statSync(absolute).isFile()) return [relative];
  const result = [];
  for (const entry of fs.readdirSync(absolute, { withFileTypes: true })) {
    const child = path.join(relative, entry.name);
    if (entry.isDirectory()) result.push(...walk(child));
    else if (entry.isFile()) result.push(child);
  }
  return result;
}

function assertSemver(value, label) {
  assert.match(
    value,
    /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/,
    `${label} must be an exact semantic version`,
  );
}

function assertRevision(value, label) {
  assert.match(value, /^[0-9a-f]{40}$/, `${label} must be an exact Git revision`);
}

test('canonical Project Forge npm package identity', () => {
  const pkg = readJson('package.json');
  const lock = readJson('package-lock.json');
  const components = readJson('assets/components.json');

  assert.equal(pkg.name, '@mriekki/project-forge');
  assertSemver(pkg.version, 'package version');
  assert.deepEqual(pkg.bin, { 'project-forge': 'bin/project-forge.mjs' });

  assert.equal(lock.name, pkg.name);
  assert.equal(lock.version, pkg.version);
  assert.equal(lock.packages[''].name, pkg.name);
  assert.equal(lock.packages[''].version, pkg.version);
  assert.deepEqual(lock.packages[''].bin, pkg.bin);

  assert.equal(components.schemaVersion, 2);
  assert.equal(components.package, pkg.name);
  assert.equal(components.version, pkg.version);
  assert.equal(components.defaultProfile, 'greenfield-project');

  assertRevision(components.components.core.revision, 'Core revision');
  assertSemver(components.components.core.version, 'Core version');
  assert.equal(Object.hasOwn(components.components.core, 'repository'), false);
  assert.equal(Object.hasOwn(components.components.core, 'commit'), false);

  assertRevision(components.components.deployment.revision, 'Deployment revision');
  assert.equal(components.components.deployment.distribution, 'greenfield-project');
  assert.equal(Object.hasOwn(components.components.deployment, 'repository'), false);
  assert.equal(Object.hasOwn(components.components.deployment, 'commit'), false);
});

test('CLI apply success line uses canonical Project Forge identity', () => {
  const cli = fs.readFileSync(path.join(root, 'src', 'cli.mjs'), 'utf8');
  assert.match(
    cli,
    /console\.log\(`\\nProject Forge \$\{command\}: PASS \(\$\{packageData\.pkg\.name\}@\$\{packageData\.pkg\.version\}\)`\);/,
  );
});

test('public Builder guidance routes managed updates through Project Forge instead of floating npm latest', () => {
  const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8');
  assert.match(readme, /\/project-forge-update/);
  assert.match(readme, /exact approved package/i);
  assert.doesNotMatch(readme, /@latest\s+(?:update|status|check)\b/i);
});

test('active package and release surfaces do not expose private foundational repository names', () => {
  const forbidden = [
    'mriekki/' + 'project-forge-' + 'core',
    'mriekki/' + 'project-forge-' + 'deployment-kit',
    'mriekki/' + 'project-forge-' + 'bootstrap',
    'mriekki/' + 'project-forge-' + 'adoption-kit',
  ];
  const roots = [
    'package.json',
    'package-lock.json',
    'bin',
    'src',
    'scripts',
    'assets',
    'docs/RELEASE_PROCESS.md',
    '.github/skills/release-project-forge',
    '.github/workflows/npm-publish.yml',
    'test/assembly.test.mjs',
    'test/engine.test.mjs',
    'test/release.test.mjs',
    'test/project-forge-package-identity.test.mjs',
  ];
  const hits = [];
  for (const relative of roots.flatMap(walk)) {
    const text = fs.readFileSync(path.join(root, relative), 'utf8');
    for (const name of forbidden) {
      if (text.includes(name)) hits.push(`${relative}: ${name}`);
    }
  }
  assert.deepEqual(hits, []);
});

test('package and release surfaces contain no retired identity or predecessor project terminology', () => {
  const lower = 'le' + 'an';
  const title = lower[0].toUpperCase() + lower.slice(1);
  const upper = lower.toUpperCase();
  const predecessor = 'po' + 'c';
  const retiredIdentityPattern = new RegExp(
    `(?<![A-Za-z0-9])(?:${lower}|${title}|${upper})(?:(?=[^A-Za-z0-9]|$)|(?=[A-Z]))|${title}(?=[A-Z])`,
  );
  const predecessorProjectPattern = new RegExp(`(?:\\b${predecessor}s?\\b|${predecessor}[-_])`, 'i');
  const roots = [
    'package.json', 'package-lock.json', 'README.md', 'bin', 'src', 'scripts', 'assets',
    'docs/RELEASE_PROCESS.md', '.github/skills', '.github/workflows',
    'test/assembly.test.mjs', 'test/cli.test.mjs', 'test/engine.test.mjs',
    'test/release.test.mjs', 'test/project-forge-package-identity.test.mjs',
  ];
  const hits = [];
  for (const relative of roots.flatMap(walk)) {
    if (retiredIdentityPattern.test(relative) || predecessorProjectPattern.test(relative)) hits.push(`PATH ${relative}`);
    const text = fs.readFileSync(path.join(root, relative), 'utf8');
    text.split(/\r?\n/).forEach((line, index) => {
      if (retiredIdentityPattern.test(line) || predecessorProjectPattern.test(line)) hits.push(`${relative}:${index + 1}:${line.trim()}`);
    });
  }
  assert.deepEqual(hits, []);
});
