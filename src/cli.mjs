import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import readline from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { applyBootstrapMigrations, planBootstrapMigrations } from './bootstrap-migrations.mjs';
import { applyProfile, checkProfile, loadProjectForgeBaseline, planProfile } from './engine.mjs';
import { loadPackageData } from './package-data.mjs';

function parseArgs(argv) {
  const options = { acceptedRetired: new Map() };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') options.help = true;
    else if (arg === '--apply' || arg === '--yes') options.apply = true;
    else if (arg === '--root') options.root = argv[++i];
    else if (arg === '--profile') options.profile = argv[++i];
    else if (arg === '--consumer') options.consumer = argv[++i];
    else if (arg === '--consumer-baseline') options.consumerBaseline = argv[++i];
    else if (arg === '--accept-retired') {
      const value = argv[++i] ?? '';
      const index = value.indexOf(':');
      if (index <= 0) throw new Error('--accept-retired must use component:path');
      const component = value.slice(0, index);
      const retiredPath = value.slice(index + 1);
      if (!options.acceptedRetired.has(component)) options.acceptedRetired.set(component, new Set());
      options.acceptedRetired.get(component).add(retiredPath);
    } else if (arg.startsWith('-')) throw new Error(`Unknown option: ${arg}`);
    else positional.push(arg);
  }
  return { command: positional[0] ?? 'help', options };
}

function inferConsumer(root) {
  try {
    const origin = execFileSync('git', ['-C', root, 'config', '--get', 'remote.origin.url'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    if (origin) {
      const normalized = origin.replace(/\\/g, '/').replace(/\.git$/, '');
      const match = normalized.match(/[:/]([^/:]+\/[^/]+)$/);
      if (match) return match[1].split('/').pop();
    }
  } catch {}
  return path.basename(root);
}

function printPlan(plan, bootstrapMigrations = { rows: [], unsafe: [] }) {
  console.log(`Project Forge profile: ${plan.profileName}`);
  if (bootstrapMigrations.rows.length) {
    console.log('\nBOOTSTRAP MIGRATIONS');
    for (const row of bootstrapMigrations.rows) console.log(`${row.state.padEnd(30)} ${row.path}`);
  }
  for (const component of plan.plans) {
    console.log(`\n${component.componentId.toUpperCase()} ${component.component.commit}`);
    for (const row of component.rows) console.log(`${row.state.padEnd(20)} ${row.path}`);
    for (const retired of component.retired) console.log(`${retired.state.padEnd(20)} ${retired.path}`);
  }
  const unsafe = [...bootstrapMigrations.unsafe, ...plan.unsafe];
  console.log(`\nUnsafe drift/conflicts: ${unsafe.length}`);
  for (const item of unsafe) console.log(`  - ${item.owner ?? item.component}: ${item.state}: ${item.path}${item.detail ? ` — ${item.detail}` : ''}`);
}

async function shouldApply(options) {
  if (options.apply) return true;
  if (!input.isTTY || !output.isTTY) return false;
  const rl = readline.createInterface({ input, output });
  try {
    const answer = (await rl.question('Apply this safe Project Forge asset plan? [y/N] ')).trim().toLowerCase();
    return answer === 'y' || answer === 'yes';
  } finally {
    rl.close();
  }
}

function usage(command) {
  const commandUsage = {
    install: 'project-forge install [--root PATH] [--profile NAME] [--apply|--yes] [--consumer NAME] [--consumer-baseline LABEL] [--accept-retired component:path]',
    update: 'project-forge update [--root PATH] [--profile NAME] [--apply|--yes] [--accept-retired component:path]',
    status: 'project-forge status [--root PATH] [--profile NAME]',
    check: 'project-forge check [--root PATH] [--profile NAME]',
    version: 'project-forge version'
  };

  if (commandUsage[command]) {
    console.log(`@mriekki/project-forge\n\nUsage:\n  ${commandUsage[command]}\n`);
    return;
  }

  console.log(`@mriekki/project-forge\n\nCommands:\n  install   Preview/install bundled Project Forge assets\n  update    Preview/update to this package's bundled Project Forge assets\n  status    Show installed umbrella/component provenance\n  check     Verify managed files and baselines exactly match this package\n  version   Show package version\n\nCommon options:\n  --root PATH\n  --profile greenfield-project\n  --apply | --yes\n  --consumer NAME\n  --consumer-baseline LABEL\n  --accept-retired core:path\n  -h, --help\n`);
}

export async function run(argv = process.argv.slice(2), packageData = loadPackageData()) {
  const { command, options } = parseArgs(argv);
  if (command === 'help') { usage(); return 0; }
  if (options.help) {
    if (!['install', 'update', 'status', 'check', 'version'].includes(command)) throw new Error(`Unknown command: ${command}`);
    usage(command);
    return 0;
  }
  if (command === 'version') { console.log(`${packageData.pkg.name} ${packageData.pkg.version}`); return 0; }
  const root = path.resolve(options.root ?? process.cwd());
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) throw new Error(`Repository root not found: ${root}`);
  const installed = loadProjectForgeBaseline(root);
  const profile = options.profile ?? installed.profile ?? packageData.assets.defaultProfile;

  if (command === 'status') {
    if (!Object.keys(installed).length) {
      console.log(`Project Forge: not installed\nAvailable package: ${packageData.pkg.name}@${packageData.pkg.version}\nProfile: ${profile}`);
      return 0;
    }
    console.log(`Project Forge package: ${installed.package}@${installed.version}`);
    console.log(`Available package: ${packageData.pkg.name}@${packageData.pkg.version}`);
    console.log(`Profile: ${installed.profile}`);
    for (const [name, component] of Object.entries(installed.components ?? {})) {
      console.log(`${name}: ${component.version ? component.version + ' @ ' : ''}${component.commit}`);
    }
    return 0;
  }

  if (command === 'check') {
    const result = checkProfile(packageData, profile, root);
    const bootstrapMigrations = planBootstrapMigrations(packageData, root);
    const bootstrapCurrent = bootstrapMigrations.rows.length === 0 && bootstrapMigrations.unsafe.length === 0;
    console.log(`Project Forge package baseline current: ${result.projectForgeCurrent ? 'yes' : 'no'}`);
    console.log(`Bootstrap generated verifier: ${bootstrapCurrent ? 'PASS' : 'STALE OR UNSUPPORTED'}`);
    for (const component of result.plan.plans) {
      const clean = component.metadataCurrent && component.rows.every((row) => row.state === 'SAME') && component.retired.length === 0;
      console.log(`${component.componentId}: ${clean ? 'PASS' : 'STALE OR DRIFTED'}`);
    }
    const clean = result.clean && bootstrapCurrent;
    console.log(`Project Forge check: ${clean ? 'PASS' : 'STALE OR DRIFTED'}`);
    return clean ? 0 : 1;
  }

  if (!['install', 'update'].includes(command)) throw new Error(`Unknown command: ${command}`);
  if (command === 'install' && Object.keys(installed).length) throw new Error('PROJECT_FORGE_BASELINE.json already exists; use update instead of install');
  if (command === 'update' && !Object.keys(installed).length) throw new Error('PROJECT_FORGE_BASELINE.json is missing; use install first');
  if (installed.profile && installed.profile !== profile) throw new Error(`Installed Project Forge profile is ${installed.profile}; refusing implicit profile change to ${profile}`);

  const bootstrapMigrations = planBootstrapMigrations(packageData, root);
  const plan = planProfile(packageData, profile, root, options.acceptedRetired);
  printPlan(plan, bootstrapMigrations);
  if (plan.unsafe.length || bootstrapMigrations.unsafe.length) {
    console.log('\nRefusing apply. Resolve drift/conflicts or the unsupported Bootstrap migration and preview again. No managed files were changed.');
    return 2;
  }
  const apply = await shouldApply(options);
  if (!apply) {
    console.log('\nPreview only. Re-run with --apply, or run interactively and approve the prompt.');
    return 0;
  }
  const baselineConsumers = [...new Set(plan.plans.map((item) => item.baseline.consumer).filter(Boolean))];
  const baselineLabels = [...new Set(plan.plans.map((item) => item.baseline.consumerBaseline).filter(Boolean))];
  if (baselineConsumers.length > 1) throw new Error(`Component baselines disagree on consumer identity: ${baselineConsumers.join(', ')}`);
  if (baselineLabels.length > 1) throw new Error(`Component baselines disagree on consumer baseline: ${baselineLabels.join(', ')}`);
  const consumer = options.consumer ?? installed.consumer ?? baselineConsumers[0] ?? inferConsumer(root);
  const consumerBaseline = options.consumerBaseline ?? installed.consumerBaseline ?? baselineLabels[0] ?? `${packageData.pkg.name}@${packageData.pkg.version}`;
  applyBootstrapMigrations(packageData, bootstrapMigrations, root);
  applyProfile(packageData, plan, root, consumer, consumerBaseline);
  console.log(`\nProject Forge ${command}: PASS (${packageData.pkg.name}@${packageData.pkg.version})`);
  return 0;
}
