import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import readline from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { applyBootstrapMigrations, planBootstrapMigrations } from './bootstrap-migrations.mjs';
import { applyProfile, applyRepair, checkProfile, loadProjectForgeBaseline, planProfile, planRepair, resolveUnder } from './engine.mjs';
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
  if (positional.length > 3) throw new Error('Unexpected positional arguments');
  if (positional[0] === 'enable') {
    options.capability = positional[1];
    options.target = positional[2];
  } else if (positional.length > 1) throw new Error('Unexpected positional arguments');
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

export function componentRevisionForDisplay(component) {
  const revision = component?.revision ?? component?.commit;
  return typeof revision === 'string' && revision ? revision : '<unknown revision>';
}

function printPlan(plan, bootstrapMigrations = { rows: [], unsafe: [] }) {
  console.log(`Project Forge profile: ${plan.profileName}`);
  if (bootstrapMigrations.rows.length) {
    console.log('\nBOOTSTRAP MIGRATIONS');
    for (const row of bootstrapMigrations.rows) console.log(`${row.state.padEnd(30)} ${row.path}`);
  }
  for (const component of plan.plans) {
    console.log(`\n${component.componentId.toUpperCase()} ${componentRevisionForDisplay(component.component)}`);
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
    enable: 'project-forge enable feedback [--root PATH] [--apply|--yes]\n  project-forge enable work-items github-issues [--root PATH] [--apply|--yes]',
    repair: 'project-forge repair [--root PATH] [--profile NAME] [--apply|--yes]',
    status: 'project-forge status [--root PATH] [--profile NAME]',
    check: 'project-forge check [--root PATH] [--profile NAME]',
    version: 'project-forge version'
  };

  if (commandUsage[command]) {
    console.log(`@mriekki/project-forge\n\nUsage:\n  ${commandUsage[command]}\n`);
    return;
  }

  console.log(`@mriekki/project-forge\n\nCommands:\n  install   Preview/install bundled Project Forge assets\n  update    Preview/update to this package's bundled Project Forge assets\n  enable    Explicitly opt an existing Project into an optional capability\n  repair    Restore missing managed files from exactly this installed package only\n  status    Show installed umbrella/component provenance\n  check     Verify managed files and baselines exactly match this package\n  version   Show package version\n\nEnable options:\n  feedback\n  work-items github-issues\n\nCommon options:\n  --root PATH\n  --profile greenfield-project\n  --apply | --yes\n  --consumer NAME\n  --consumer-baseline LABEL\n  --accept-retired core:path\n  -h, --help\n`);
}

export async function run(argv = process.argv.slice(2), packageData = loadPackageData()) {
  const { command, options } = parseArgs(argv);
  if (command === 'help') { usage(); return 0; }
  if (options.help) {
    if (!['install', 'update', 'enable', 'repair', 'status', 'check', 'version'].includes(command)) throw new Error(`Unknown command: ${command}`);
    usage(command);
    return 0;
  }
  if (command === 'version') { console.log(`${packageData.pkg.name} ${packageData.pkg.version}`); return 0; }
  const root = path.resolve(options.root ?? process.cwd());
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) throw new Error(`Repository root not found: ${root}`);
  const installed = loadProjectForgeBaseline(root);
  const profile = options.profile ?? installed.profile ?? packageData.assets.defaultProfile;

  if (command === 'enable') {
    if (options.capability === 'work-items') {
      if (options.target !== 'github-issues') {
        throw new Error('Usage: project-forge enable work-items github-issues');
      }
      if (!Object.keys(installed).length) {
        throw new Error('No Project Forge baseline; install the Project Forge profile first.');
      }
      if (installed.schemaVersion !== 2 ||
          !packageData.assets.profiles[installed.profile]?.components?.includes('core')) {
        throw new Error('GitHub Issues work-item opt-in requires an intact schema-v2 Project Forge profile; update or reconcile the Project first.');
      }
      if (options.profile && options.profile !== installed.profile) {
        throw new Error(`Work-item opt-in must retain the installed Project Forge profile: ${installed.profile}`);
      }
      const recordedComponents = installed.components;
      const expectedComponents = packageData.assets.profiles[installed.profile].components;
      if (!recordedComponents || typeof recordedComponents !== 'object' ||
          Array.isArray(recordedComponents) ||
          Object.keys(recordedComponents).sort().join('\0') !== [...expectedComponents].sort().join('\0')) {
        throw new Error('Installed component set does not match the selected profile; refusing work-item transition.');
      }
      for (const componentId of expectedComponents) {
        const recorded = recordedComponents[componentId];
        const baselinePath = componentId === 'core' ? 'CORE_BASELINE.json'
          : componentId === 'deployment' ? 'DEPLOYMENT_BASELINE.json'
            : componentId === 'authentication' ? 'AUTHENTICATION_BASELINE.json'
              : componentId === 'feedback' ? 'FEEDBACK_BASELINE.json' : null;
        if (!baselinePath) throw new Error(`Unsupported component for work-item opt-in: ${componentId}`);
        const componentBaseline = JSON.parse(fs.readFileSync(
          resolveUnder(root, baselinePath, 'component baseline'), 'utf8'
        ));
        if (!recorded || typeof recorded !== 'object' ||
            componentBaseline.schemaVersion !== 2 ||
            componentBaseline.component !== componentId ||
            componentBaseline.revision !== recorded.revision ||
            componentBaseline.distribution !== recorded.distribution ||
            (componentBaseline.version ?? null) !== (recorded.version ?? null)) {
          throw new Error(`Installed ${componentId} baseline does not match the umbrella provenance; refusing work-item transition.`);
        }
      }
      if (!packageData.assets.components.core.profileVariants?.['existing-github']) {
        throw new Error('This Project Forge package does not provide the GitHub Issues work-item transition.');
      }
      const selectedVariants = { ...(installed.componentVariants ?? {}), core: 'existing-github' };
      if (installed.componentVariants?.core === 'existing-github') {
        if (checkProfile(packageData, installed.profile, root).clean) {
          console.log('Project Forge GitHub Issues work-item source is already enabled; no changes made.');
          return 0;
        }
      }

      const plan = planProfile(
        packageData, installed.profile, root, options.acceptedRetired, selectedVariants
      );
      printPlan(plan);
      if (plan.unsafe.length) {
        console.log('\nRefusing work-item opt-in. Resolve managed-file drift/conflicts and preview again. No managed files were changed.');
        return 2;
      }
      if (!await shouldApply(options)) {
        console.log('\nPreview only. Re-run with --apply, or run interactively and approve the prompt.');
        return 0;
      }
      applyProfile(
        packageData, plan, root,
        installed.consumer ?? inferConsumer(root),
        installed.consumerBaseline ?? `${packageData.pkg.name}@${packageData.pkg.version}`
      );
      if (!checkProfile(packageData, installed.profile, root).clean) {
        throw new Error('GitHub Issues work-item opt-in completed but final managed-file verification is not clean.');
      }
      console.log(`\nProject Forge GitHub Issues work-item opt-in: PASS (${packageData.pkg.name}@${packageData.pkg.version})`);
      return 0;
    }

    if (options.capability !== 'feedback' || options.target) {
      throw new Error('Usage: project-forge enable feedback');
    }
    if (!Object.keys(installed).length) throw new Error('No Project Forge baseline; install the Project Forge profile first.');
    if (installed.schemaVersion !== 2 ||
        !['greenfield-project', 'greenfield-household-project'].includes(installed.profile)) {
      throw new Error('Feedback opt-in requires an intact schema-v2 standard or household Auth profile; update or reconcile the Project first.');
    }

    const baseProfile = packageData.assets.profiles[installed.profile];
    if (!baseProfile || !Array.isArray(baseProfile.components)) {
      throw new Error(`The package does not provide the installed base profile: ${installed.profile}`);
    }
    const recordedComponents = installed.components;
    const baseComponents = [...baseProfile.components];
    if (!recordedComponents || typeof recordedComponents !== 'object' || Array.isArray(recordedComponents) ||
        Object.keys(recordedComponents).sort().join('\0') !== [...baseComponents].sort().join('\0')) {
      throw new Error('Installed component set does not match the selected base profile; refusing capability transition.');
    }
    for (const componentId of baseComponents) {
      const recorded = recordedComponents[componentId];
      const baselinePath = componentId === 'core' ? 'CORE_BASELINE.json'
        : componentId === 'deployment' ? 'DEPLOYMENT_BASELINE.json'
          : componentId === 'authentication' ? 'AUTHENTICATION_BASELINE.json' : null;
      if (!baselinePath) throw new Error(`Unsupported base component for Feedback opt-in: ${componentId}`);
      const componentBaseline = JSON.parse(fs.readFileSync(resolveUnder(root, baselinePath, 'component baseline'), 'utf8'));
      if (!recorded || typeof recorded !== 'object' ||
          componentBaseline.schemaVersion !== 2 ||
          componentBaseline.component !== componentId ||
          componentBaseline.revision !== recorded.revision ||
          componentBaseline.distribution !== recorded.distribution ||
          (componentBaseline.version ?? null) !== (recorded.version ?? null)) {
        throw new Error(`Installed ${componentId} baseline does not match the umbrella provenance; refusing capability transition.`);
      }
    }

    const targetProfile = installed.profile === 'greenfield-household-project'
      ? 'greenfield-household-feedback-project'
      : 'greenfield-feedback-project';
    if (options.profile && options.profile !== targetProfile) {
      throw new Error(`Feedback opt-in selects ${targetProfile}; refusing a different requested profile.`);
    }
    if (!packageData.assets.components.feedback || !packageData.assets.profiles[targetProfile]) {
      throw new Error('This Project Forge package does not provide the opt-in Feedback capability.');
    }
    if (Object.hasOwn(recordedComponents, 'feedback')) {
      throw new Error('Feedback is already recorded in the installed component set.');
    }

    const bootstrapMigrations = planBootstrapMigrations(packageData, root);
    const plan = planProfile(
      packageData, targetProfile, root, options.acceptedRetired,
      installed.componentVariants ?? {}
    );
    printPlan(plan, bootstrapMigrations);
    if (plan.unsafe.length || bootstrapMigrations.unsafe.length) {
      console.log('\nRefusing opt-in. Resolve managed-file drift/conflicts or the unsupported Bootstrap migration and preview again. No managed files were changed.');
      return 2;
    }
    if (!await shouldApply(options)) {
      console.log('\nPreview only. Re-run with --apply, or run interactively and approve the prompt.');
      return 0;
    }
    applyBootstrapMigrations(packageData, bootstrapMigrations, root);
    applyProfile(
      packageData, plan, root,
      installed.consumer ?? inferConsumer(root),
      installed.consumerBaseline ?? `${packageData.pkg.name}@${packageData.pkg.version}`
    );
    if (!checkProfile(packageData, targetProfile, root).clean) {
      throw new Error('Feedback opt-in completed but final managed-file verification is not clean.');
    }
    console.log(`\nProject Forge Feedback opt-in: PASS (${packageData.pkg.name}@${packageData.pkg.version})`);
    return 0;
  }

  if (command === 'status') {
    if (!Object.keys(installed).length) {
      console.log(`Project Forge: not installed\nAvailable package: ${packageData.pkg.name}@${packageData.pkg.version}\nProfile: ${profile}`);
      return 0;
    }
    console.log(`Project Forge package: ${installed.package}@${installed.version}`);
    console.log(`Available package: ${packageData.pkg.name}@${packageData.pkg.version}`);
    console.log(`Profile: ${installed.profile}`);
    if (installed.componentVariants?.core === 'existing-github') {
      console.log('Work-item source: GitHub Issues');
    }
    for (const [name, component] of Object.entries(installed.components ?? {})) {
      console.log(`${name}: ${component.version ? component.version + ' @ ' : ''}${componentRevisionForDisplay(component)}`);
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

  if (command === 'repair') {
    if (!Object.keys(installed).length) throw new Error('No Project Forge baseline; install first.');
    if (installed.profile !== profile) throw new Error('Repair must use the exact installed profile.');
    const bootstrap = planBootstrapMigrations(packageData, root);
    const plan = planRepair(packageData, profile, root);
    console.log(`Project Forge repair: ${plan.missing.length} missing managed file(s)`);
    for (const file of plan.missing) console.log(`  MISSING ${file.component}: ${file.path}`);
    for (const blocker of plan.blockers) console.log(`  BLOCKED: ${blocker}`);
    if (bootstrap.rows.length || bootstrap.unsafe.length || !plan.safe) {
      console.log('Refusing repair: stale package, migration, local edits, or conflicting files. No changes made.');
      return 2;
    }
    if (plan.missing.length === 0) {
      console.log('Project Forge repair: already complete; no changes made.');
      return 0;
    }
    if (!await shouldApply(options)) {
      console.log('Preview only. Re-run with --apply after reviewing missing managed files.');
      return 0;
    }
    applyRepair(packageData, profile, root);
    if (!checkProfile(packageData, profile, root).clean) {
      throw new Error('Repair completed but final managed-file verification is not clean.');
    }
    console.log(`Project Forge repair: PASS (${packageData.pkg.name}@${packageData.pkg.version})`);
    return 0;
  }

  if (!['install', 'update'].includes(command)) throw new Error(`Unknown command: ${command}`);
  if (command === 'install' && Object.keys(installed).length) throw new Error('PROJECT_FORGE_BASELINE.json already exists; use update instead of install');
  if (command === 'update' && !Object.keys(installed).length) throw new Error('PROJECT_FORGE_BASELINE.json is missing; use install first');
  if (installed.profile && installed.profile !== profile) throw new Error(`Installed Project Forge profile is ${installed.profile}; refusing implicit profile change to ${profile}`);

  const bootstrapMigrations = planBootstrapMigrations(packageData, root);
  const plan = planProfile(
    packageData, profile, root, options.acceptedRetired,
    installed.componentVariants ?? {}
  );
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
