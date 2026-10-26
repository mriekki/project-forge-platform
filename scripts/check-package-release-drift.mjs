import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function runGit(root, args) {
  return execFileSync('git', ['-C', root, ...args], {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  }).trim();
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function normalizeEntry(value) {
  return value.replace(/\\/g, '/').replace(/^\.\/+/, '');
}

export function packagePayloadEntries(pkg) {
  const entries = new Set([
    'package.json',
    'README',
    'README.md',
    'README.txt',
    'LICENSE',
    'LICENSE.md',
    'LICENCE',
    'LICENCE.md'
  ]);

  for (const value of pkg?.files ?? []) {
    if (typeof value !== 'string' || !value.trim()) continue;
    entries.add(normalizeEntry(value.trim()));
  }

  return [...entries];
}

export function packagePayloadChanges(changedFiles, entries) {
  const normalizedEntries = entries.map(normalizeEntry);
  return changedFiles
    .map(normalizeEntry)
    .filter((file) => normalizedEntries.some((entry) => {
      if (entry.endsWith('/')) return file.startsWith(entry);
      return file === entry;
    }))
    .sort();
}

export function parseArgs(argv) {
  const result = { json: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--baseline') result.baseline = argv[++i];
    else if (arg === '--json') result.json = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }

  if (!/^[0-9a-f]{40}$/.test(result.baseline ?? '')) {
    throw new Error('--baseline must be an exact 40-character lowercase commit SHA');
  }

  return result;
}

export function inspectPackageReleaseDrift({ baseline }, root = ROOT) {
  const packageRoot = path.resolve(root);
  const pkg = readJson(path.join(packageRoot, 'package.json'));
  const head = runGit(packageRoot, ['rev-parse', 'HEAD']);

  runGit(packageRoot, ['rev-parse', '--verify', `${baseline}^{commit}`]);
  try {
    execFileSync('git', ['-C', packageRoot, 'merge-base', '--is-ancestor', baseline, head], {
      cwd: packageRoot,
      stdio: 'ignore'
    });
  } catch {
    throw new Error(`Published source ${baseline} is not an ancestor of current HEAD ${head}`);
  }

  const baselinePackage = JSON.parse(runGit(packageRoot, ['show', `${baseline}:package.json`]));
  if (baselinePackage.name !== pkg.name || baselinePackage.version !== pkg.version) {
    throw new Error(
      `Published source ${baseline} is ${baselinePackage.name ?? '<unknown>'}@${baselinePackage.version ?? '<unknown>'}, ` +
      `but current source is ${pkg.name}@${pkg.version}`
    );
  }

  const diff = runGit(packageRoot, ['diff', '--name-only', `${baseline}..${head}`, '--']);
  const changedFiles = diff ? diff.split(/\r?\n/).filter(Boolean) : [];
  const payloadChanges = packagePayloadChanges(changedFiles, packagePayloadEntries(pkg));

  return {
    package: pkg.name,
    version: pkg.version,
    baseline,
    head,
    releaseNeeded: payloadChanges.length > 0,
    payloadChanges
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const args = parseArgs(process.argv.slice(2));
    const result = inspectPackageReleaseDrift(args);
    if (args.json) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      console.log(`Package: ${result.package}@${result.version}`);
      console.log(`Published Platform source: ${result.baseline}`);
      console.log(`Current Platform source: ${result.head}`);
      console.log(`Shipped Platform payload drift: ${result.releaseNeeded ? 'YES' : 'NO'}`);
      for (const file of result.payloadChanges) console.log(`- ${file}`);
    }
  } catch (error) {
    console.error(`Package release drift check failed: ${error.message}`);
    process.exitCode = 2;
  }
}
