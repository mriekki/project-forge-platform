import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { assembleAssets } from './assemble-assets.mjs';
import { verifyAssets } from './verify-assets.mjs';
import { loadPackageData } from '../src/package-data.mjs';

export function resolveNpmInvocation(args, options = {}) {
  const platform = options.platform ?? process.platform;
  if (platform !== 'win32') return { command: 'npm', args };

  const execPath = options.execPath ?? process.execPath;
  const existsSync = options.existsSync ?? fs.existsSync;
  const npmCli = path.win32.join(path.win32.dirname(execPath), 'node_modules', 'npm', 'bin', 'npm-cli.js');
  if (!existsSync(npmCli)) {
    throw new Error(`Unable to locate npm CLI next to the Node executable: ${npmCli}`);
  }
  return { command: execPath, args: [npmCli, ...args] };
}

export function npmPackArgs(destination) {
  // Release preparation already verifies the assembled assets explicitly. Disable
  // lifecycle scripts here so prepack stdout cannot corrupt npm pack --json output.
  return ['pack', '--json', '--ignore-scripts', '--pack-destination', destination];
}

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: options.cwd,
    encoding: 'utf8',
    stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    env: { ...process.env, ...(options.env ?? {}) }
  });
}

function runNpm(args, options = {}) {
  const invocation = resolveNpmInvocation(args);
  return run(invocation.command, invocation.args, options);
}

function git(root, args) {
  return run('git', ['-C', root, ...args], { cwd: root, capture: true }).trim();
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function assertCleanTracked(root, label) {
  const status = git(root, ['status', '--porcelain', '--untracked-files=no']);
  if (status) throw new Error(`${label} has tracked working-tree changes`);
}

function assertReleaseSource(packageData) {
  const root = packageData.root;
  assertCleanTracked(root, 'Project Forge Platform checkout');
  const origin = git(root, ['remote', 'get-url', 'origin']);
  if (!/github\.com[:/]mriekki\/project-forge-platform(?:\.git)?$/i.test(origin.replace(/\\/g, '/'))) {
    throw new Error(`Unexpected Project Forge Platform origin: ${origin}`);
  }
  run('git', ['-C', root, 'fetch', '--quiet', 'origin', 'main'], { cwd: root });
  const head = git(root, ['rev-parse', 'HEAD']);
  const main = git(root, ['rev-parse', 'origin/main']);
  if (head !== main) throw new Error(`Release checkout is not exact origin/main: HEAD ${head}, origin/main ${main}`);
  return head;
}

function pack(packageData, destination) {
  fs.mkdirSync(destination, { recursive: true });
  const raw = runNpm(npmPackArgs(destination), { cwd: packageData.root, capture: true });
  const result = JSON.parse(raw);
  if (!Array.isArray(result) || result.length !== 1 || !result[0].filename) throw new Error('Unexpected npm pack output');
  return { metadata: result[0], file: path.join(destination, result[0].filename) };
}

function smokeTarball(tarball, expectedVersion) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'project-forge-release-smoke-'));
  try {
    fs.writeFileSync(path.join(temp, 'package.json'), JSON.stringify({ private: true }) + '\n');
    runNpm(['install', '--ignore-scripts', '--no-audit', '--no-fund', tarball], { cwd: temp });
    const bin = path.join(temp, 'node_modules', '@mriekki', 'project-forge', 'bin', 'project-forge.mjs');
    const directVersion = run(process.execPath, [bin, 'version'], { cwd: temp, capture: true }).trim();
    if (directVersion !== `@mriekki/project-forge ${expectedVersion}`) throw new Error(`Tarball version smoke mismatch: ${directVersion}`);
    const npmVersion = runNpm(['exec', '--', 'project-forge', 'version'], { cwd: temp, capture: true }).trim();
    if (npmVersion !== `@mriekki/project-forge ${expectedVersion}`) throw new Error(`Tarball npm bin smoke mismatch: ${npmVersion}`);
    const consumer = path.join(temp, 'consumer');
    fs.mkdirSync(consumer);
    run(process.execPath, [bin, 'install', '--root', consumer, '--apply', '--consumer', 'release-smoke', '--consumer-baseline', `@mriekki/project-forge@${expectedVersion}`], { cwd: temp });
    run(process.execPath, [bin, 'check', '--root', consumer], { cwd: temp });
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

export function parseArgs(argv) {
  const values = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--core-root') values.core = argv[++i];
    else if (arg === '--deployment-root') values.deployment = argv[++i];
    else if (arg === '--authentication-root') values.authentication = argv[++i];
    else if (arg === '--output') values.output = argv[++i];
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!values.core || !values.deployment) throw new Error('--core-root and --deployment-root are required');
  return values;
}

export function prepareRelease(args, packageData = loadPackageData()) {
  const sourceCommit = assertReleaseSource(packageData);
  runNpm(['test'], { cwd: packageData.root });
  const assembly = assembleAssets(packageData, {
    core: args.core,
    deployment: args.deployment,
    authentication: args.authentication
  });
  const assetCount = verifyAssets(packageData);

  const releaseRoot = path.resolve(args.output ?? path.join(packageData.root, 'dist', 'release'));
  const firstDir = path.join(releaseRoot, '.pack-a');
  const secondDir = path.join(releaseRoot, '.pack-b');
  fs.rmSync(releaseRoot, { recursive: true, force: true });
  fs.mkdirSync(releaseRoot, { recursive: true });

  try {
    const first = pack(packageData, firstDir);
    const second = pack(packageData, secondDir);
    const firstHash = sha256(first.file);
    const secondHash = sha256(second.file);
    if (firstHash !== secondHash) throw new Error(`npm pack is not reproducible: ${firstHash} != ${secondHash}`);
    smokeTarball(first.file, packageData.pkg.version);

    const finalTarball = path.join(releaseRoot, first.metadata.filename);
    fs.copyFileSync(first.file, finalTarball);
    const manifest = {
      schemaVersion: 1,
      package: packageData.pkg.name,
      version: packageData.pkg.version,
      sourceRepository: 'mriekki/project-forge-platform',
      sourceCommit,
      components: assembly.components,
      assetCount,
      tarball: {
        filename: path.basename(finalTarball),
        sha256: firstHash,
        shasum: first.metadata.shasum,
        integrity: first.metadata.integrity,
        fileCount: first.metadata.entryCount,
        unpackedSize: first.metadata.unpackedSize
      }
    };
    fs.writeFileSync(path.join(releaseRoot, 'RELEASE_MANIFEST.json'), JSON.stringify(manifest, null, 2) + '\n');
    return manifest;
  } finally {
    fs.rmSync(firstDir, { recursive: true, force: true });
    fs.rmSync(secondDir, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const args = parseArgs(process.argv.slice(2));
    const manifest = prepareRelease(args);
    console.log(`Release candidate ready: ${manifest.package}@${manifest.version}`);
    console.log(`Tarball: dist/release/${manifest.tarball.filename}`);
    console.log(`SHA-256: ${manifest.tarball.sha256}`);
    console.log(`Source: ${manifest.sourceCommit}`);
  } catch (error) {
    console.error(`Release preparation failed: ${error.message}`);
    process.exitCode = 2;
  }
}
