import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { componentEntries, sha256File } from '../src/engine.mjs';
import { loadPackageData, readJson } from '../src/package-data.mjs';

export function verifyAssets(packageData = loadPackageData()) {
  const assemblyPath = path.join(packageData.root, 'assets', 'generated', 'ASSEMBLY.json');
  if (!fs.existsSync(assemblyPath)) throw new Error('assets/generated/ASSEMBLY.json is missing; assemble exact component snapshots before packaging');
  const assembly = readJson(assemblyPath);
  if (assembly.schemaVersion !== 2) throw new Error('Generated assembly schema is stale');
  if (assembly.package !== packageData.pkg.name || assembly.version !== packageData.pkg.version) throw new Error('Generated assembly package metadata is stale');
  let count = 0;
  for (const [componentId, component] of Object.entries(packageData.assets.components)) {
    const recorded = assembly.components?.[componentId];
    if (!recorded || recorded.revision !== component.revision || recorded.distribution !== component.distribution || (component.version && recorded.version !== component.version)) {
      throw new Error(`Generated ${componentId} provenance is stale`);
    }
    const recordedFiles = new Map((recorded.files ?? []).map((item) => [item.source, item]));
    for (const entry of componentEntries(packageData, componentId)) {
      const item = recordedFiles.get(entry.source);
      if (!item || item.destination !== entry.path || item.sha256 !== sha256File(entry.bundlePath)) throw new Error(`Generated ${componentId} asset mismatch: ${entry.source}`);
      count += 1;
    }
  }
  return count;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(`Project Forge asset verification: PASS (${verifyAssets()} files)`);
  } catch (error) {
    console.error(`Project Forge asset verification: FAIL: ${error.message}`);
    process.exitCode = 2;
  }
}
