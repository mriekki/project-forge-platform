import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { readJson } from './package-data.mjs';

const CORE_SAFE = new Set(['SAME', 'ADD', 'CORE_UPDATE', 'UNTRACKED_MATCH', 'BASELINE_STALE', 'REMOVE', 'RETIRED_MISSING']);
const DEPLOYMENT_SAFE = new Set(['SAME', 'ADD', 'KIT_UPDATE', 'UNTRACKED_MATCH', 'BASELINE_STALE', 'REMOVE', 'RETIRED_MISSING']);

export function safeRelative(value, label = 'path') {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} must be a non-empty relative path`);
  const normalized = value.replaceAll('\\', '/');
  if (normalized.startsWith('/') || /^[A-Za-z]:/.test(normalized)) throw new Error(`Unsafe ${label}: ${value}`);
  const parts = normalized.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..')) throw new Error(`Unsafe ${label}: ${value}`);
  return normalized;
}

export function resolveUnder(root, relative, label = 'path') {
  const rel = safeRelative(relative, label);
  const base = path.resolve(root);
  const candidate = path.resolve(base, ...rel.split('/'));
  if (candidate !== base && !candidate.startsWith(base + path.sep)) throw new Error(`${label} escapes root: ${relative}`);
  return candidate;
}

export function sha256File(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function baselineFile(componentId) {
  if (componentId === 'core') return 'CORE_BASELINE.json';
  if (componentId === 'deployment') return 'DEPLOYMENT_BASELINE.json';
  throw new Error(`Unsupported component: ${componentId}`);
}

function loadOptionalJson(file) {
  if (!fs.existsSync(file)) return {};
  const value = readJson(file);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`Invalid JSON object: ${file}`);
  return value;
}

function baselineMap(baseline, filename) {
  const items = baseline.managedPaths ?? [];
  if (Object.keys(baseline).length && (!Array.isArray(items) || items.length === 0)) {
    throw new Error(`Invalid ${filename}: managedPaths is missing or empty`);
  }
  const map = new Map();
  for (const item of items) {
    if (!item?.path || !item?.sha256 || !item?.source) throw new Error(`Invalid managedPaths entry in ${filename}`);
    if (map.has(item.path)) throw new Error(`Duplicate managed path in ${filename}: ${item.path}`);
    map.set(item.path, item);
  }
  return map;
}

function componentRevision(component) {
  const revision = component.revision ?? component.commit;
  if (typeof revision !== 'string' || !/^[0-9a-f]{40}$/i.test(revision)) throw new Error('Component revision must be an exact 40-character Git revision');
  return revision.toLowerCase();
}

export function componentEntries(packageData, componentId) {
  const component = packageData.assets.components[componentId];
  if (!component) throw new Error(`Package does not define component ${componentId}`);
  const descriptor = readJson(resolveUnder(packageData.root, component.descriptor, 'component descriptor'));
  const mappings = [];
  if (descriptor.profileSource && descriptor.profileDestination) {
    mappings.push({ source: descriptor.profileSource, path: descriptor.profileDestination });
  }
  for (const item of descriptor.mappings ?? []) mappings.push({ source: item.source, path: item.destination });
  if (!mappings.length) throw new Error(`${componentId} distribution has no mappings`);
  const seen = new Set();
  return mappings.map((entry) => {
    safeRelative(entry.source, 'source');
    safeRelative(entry.path, 'destination');
    if (seen.has(entry.path)) throw new Error(`Duplicate ${componentId} destination: ${entry.path}`);
    seen.add(entry.path);
    const bundlePath = resolveUnder(packageData.root, `${component.sourceRoot}/${entry.source}`, 'bundled source');
    if (!fs.existsSync(bundlePath) || !fs.statSync(bundlePath).isFile()) {
      throw new Error(`Missing bundled ${componentId} source: ${entry.source}`);
    }
    return { ...entry, bundlePath };
  });
}

function classifyDesired(componentId, src, dst, baselineItem) {
  const desiredHash = sha256File(src);
  if (!fs.existsSync(dst)) return { state: baselineItem ? 'LOCAL_MISSING' : 'ADD', desiredHash, currentHash: null };
  const stat = fs.lstatSync(dst);
  if (!stat.isFile() || stat.isSymbolicLink()) return { state: 'PATH_CONFLICT', desiredHash, currentHash: null };
  const currentHash = sha256File(dst);
  if (!baselineItem) return { state: currentHash === desiredHash ? 'UNTRACKED_MATCH' : 'UNTRACKED_CONFLICT', desiredHash, currentHash };
  const baselineHash = baselineItem.sha256;
  const consumerChanged = currentHash !== baselineHash;
  const sourceChanged = desiredHash !== baselineHash;
  if (!consumerChanged && !sourceChanged) return { state: 'SAME', desiredHash, currentHash };
  if (!consumerChanged && sourceChanged) return { state: componentId === 'core' ? 'CORE_UPDATE' : 'KIT_UPDATE', desiredHash, currentHash };
  if (consumerChanged && !sourceChanged) return { state: 'LOCAL_DRIFT', desiredHash, currentHash };
  if (currentHash === desiredHash) return { state: 'BASELINE_STALE', desiredHash, currentHash };
  return { state: 'CONFLICT', desiredHash, currentHash };
}

function validateBaselineIdentity(baseline, componentId, component, filename) {
  if (!Object.keys(baseline).length) return;
  if (![1, 2].includes(baseline.schemaVersion)) throw new Error(`Unsupported ${filename} schemaVersion`);
  if (baseline.schemaVersion === 2 && baseline.component !== componentId) throw new Error(`${filename} records a different component`);
  if (baseline.distribution && baseline.distribution !== component.distribution) throw new Error(`${filename} records a different distribution`);
}

function componentMetadataCurrent(baseline, componentId, component) {
  if (baseline.schemaVersion !== 2 || baseline.component !== componentId) return false;
  if (baseline.revision !== componentRevision(component) || baseline.distribution !== component.distribution) return false;
  if (componentId === 'core' && baseline.version !== component.version) return false;
  return Array.isArray(baseline.managedPaths) && baseline.managedPaths.length > 0;
}

export function planComponent(packageData, componentId, targetRoot, acceptedRetired = new Set()) {
  const component = packageData.assets.components[componentId];
  if (!component) throw new Error(`Package does not define component ${componentId}`);
  componentRevision(component);
  const filename = baselineFile(componentId);
  const baseline = loadOptionalJson(path.join(targetRoot, filename));
  validateBaselineIdentity(baseline, componentId, component, filename);

  const entries = componentEntries(packageData, componentId);
  const baseMap = baselineMap(baseline, filename);
  const rows = entries.map((entry) => {
    const dst = resolveUnder(targetRoot, entry.path, 'consumer destination');
    return { ...entry, ...classifyDesired(componentId, entry.bundlePath, dst, baseMap.get(entry.path)) };
  });
  const desired = new Set(entries.map((entry) => entry.path));
  const retired = [];
  for (const [retiredPath, item] of [...baseMap.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    if (desired.has(retiredPath)) continue;
    const dst = resolveUnder(targetRoot, retiredPath, 'retired destination');
    if (!fs.existsSync(dst)) {
      retired.push({ path: retiredPath, item, state: 'RETIRED_MISSING' });
      continue;
    }
    const stat = fs.lstatSync(dst);
    const currentHash = stat.isFile() && !stat.isSymbolicLink() ? sha256File(dst) : null;
    if (currentHash === item.sha256) {
      retired.push({ path: retiredPath, item, currentHash, state: 'REMOVE' });
    } else if (componentId === 'core' && acceptedRetired.has(retiredPath)) {
      retired.push({ path: retiredPath, item, currentHash, state: 'RETIRED_ACCEPTED' });
    } else {
      retired.push({ path: retiredPath, item, currentHash, state: 'RETIRED_DRIFT' });
    }
  }
  const safe = componentId === 'core' ? CORE_SAFE : DEPLOYMENT_SAFE;
  const unsafe = rows.filter((row) => !safe.has(row.state)).map((row) => ({ state: row.state, path: row.path }));
  for (const item of retired) {
    const isSafe = item.state === 'RETIRED_ACCEPTED' || safe.has(item.state);
    if (!isSafe) unsafe.push({ state: item.state, path: item.path });
  }
  return {
    componentId,
    component,
    filename,
    baseline,
    rows,
    retired,
    unsafe,
    metadataCurrent: componentMetadataCurrent(baseline, componentId, component)
  };
}

function buildComponentBaseline(plan, consumer, consumerBaseline) {
  const managedPaths = plan.rows.map((row) => ({ source: row.source, path: row.path, sha256: row.desiredHash }));
  return {
    schemaVersion: 2,
    component: plan.componentId,
    consumer,
    consumerBaseline,
    revision: componentRevision(plan.component),
    ...(plan.component.version ? { version: plan.component.version } : {}),
    distribution: plan.component.distribution,
    managedPaths
  };
}

export function planProfile(packageData, profileName, targetRoot, acceptedRetired = new Map()) {
  const profile = packageData.assets.profiles[profileName];
  if (!profile) throw new Error(`Unknown Project Forge profile: ${profileName}`);
  const plans = profile.components.map((id) => planComponent(packageData, id, targetRoot, acceptedRetired.get(id) ?? new Set()));
  const destinations = new Map();
  for (const plan of plans) {
    for (const row of plan.rows) {
      const owner = destinations.get(row.path);
      if (owner) throw new Error(`Managed-path collision: ${row.path} is owned by both ${owner} and ${plan.componentId}`);
      destinations.set(row.path, plan.componentId);
    }
  }
  return { profileName, profile, plans, unsafe: plans.flatMap((plan) => plan.unsafe.map((item) => ({ component: plan.componentId, ...item }))) };
}

export function applyProfile(packageData, profilePlan, targetRoot, consumer, consumerBaseline) {
  if (profilePlan.unsafe.length) throw new Error('Refusing apply: plan contains unsafe drift/conflicts');
  for (const plan of profilePlan.plans) {
    for (const row of plan.rows) {
      if (!['ADD', 'CORE_UPDATE', 'KIT_UPDATE'].includes(row.state)) continue;
      const dst = resolveUnder(targetRoot, row.path, 'consumer destination');
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(row.bundlePath, dst);
    }
    for (const retired of plan.retired) {
      if (retired.state === 'REMOVE') fs.unlinkSync(resolveUnder(targetRoot, retired.path, 'retired destination'));
    }
  }
  for (const plan of profilePlan.plans) {
    const baseline = buildComponentBaseline(plan, consumer, consumerBaseline);
    fs.writeFileSync(path.join(targetRoot, plan.filename), JSON.stringify(baseline, null, 2) + '\n');
  }
  const projectForgeBaseline = {
    schemaVersion: 2,
    package: packageData.pkg.name,
    version: packageData.pkg.version,
    profile: profilePlan.profileName,
    consumer,
    consumerBaseline,
    components: Object.fromEntries(profilePlan.plans.map((plan) => [plan.componentId, {
      revision: componentRevision(plan.component),
      ...(plan.component.version ? { version: plan.component.version } : {}),
      distribution: plan.component.distribution
    }]))
  };
  fs.writeFileSync(path.join(targetRoot, 'PROJECT_FORGE_BASELINE.json'), JSON.stringify(projectForgeBaseline, null, 2) + '\n');
  return projectForgeBaseline;
}

export function checkProfile(packageData, profileName, targetRoot) {
  const plan = planProfile(packageData, profileName, targetRoot);
  const projectForgeBaseline = loadOptionalJson(path.join(targetRoot, 'PROJECT_FORGE_BASELINE.json'));
  const projectForgeCurrent = projectForgeBaseline.schemaVersion === 2 && projectForgeBaseline.package === packageData.pkg.name && projectForgeBaseline.version === packageData.pkg.version && projectForgeBaseline.profile === profileName;
  const componentClean = plan.plans.every((component) => component.metadataCurrent && component.rows.every((row) => row.state === 'SAME') && component.retired.length === 0);
  return { clean: projectForgeCurrent && componentClean, projectForgeCurrent, plan, projectForgeBaseline };
}

export function loadProjectForgeBaseline(targetRoot) {
  return loadOptionalJson(path.join(targetRoot, 'PROJECT_FORGE_BASELINE.json'));
}
