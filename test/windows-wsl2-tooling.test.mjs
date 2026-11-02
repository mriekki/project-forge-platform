import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

async function text(path) {
  return readFile(path, 'utf8');
}

test('package ships Windows WSL2 migration tooling', async () => {
  const pkg = JSON.parse(await text('package.json'));
  assert.ok(pkg.files.includes('tools/'));

  const script = await text('tools/windows/project-forge-wsl2.ps1');
  assert.match(script, /\[switch\]\$MigrateRepositories/);
  assert.match(script, /--set-default-version 2/);
  assert.match(script, /Docker\.DockerDesktop/);
  assert.match(script, /ms-vscode-remote\.remote-wsl/);
  assert.match(script, /working tree is not clean/i);
  assert.match(script, /Windows source checkouts were NOT deleted/);
  assert.match(script, /git clone --no-hardlinks/);
});

test('Windows WSL2 guide documents safe default and rollback', async () => {
  const guide = await text('docs/WINDOWS_WSL2.md');
  assert.match(guide, /defaults Windows development to WSL2/i);
  assert.match(guide, /~\/projects/);
  assert.match(guide, /Do not install a second Docker Engine inside WSL/i);
  assert.match(guide, /does \*\*not\*\* delete the Windows source checkout/i);
  assert.match(guide, /Rollback/);
});
