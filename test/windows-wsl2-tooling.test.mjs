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
  assert.match(script, /"clone", "--no-hardlinks"/);
});

test('Windows WSL2 migration script avoids PowerShell runtime traps found in live migration', async () => {
  const script = await text('tools/windows/project-forge-wsl2.ps1');

  // PowerShell parses `$Distro:` as a scoped-variable reference unless the name is delimited.
  assert.doesNotMatch(script, /\$Distro:/);
  assert.match(script, /\$\{Distro\}:/);

  // `$HOME` is a built-in read-only variable and PowerShell variable names are case-insensitive.
  assert.doesNotMatch(script, /\$home\b/);
  assert.match(script, /\$wslHome\b/);

  // All helper invocations must pass argv explicitly so flags such as -p and -C are not
  // interpreted as parameters to Invoke-Wsl itself.
  assert.match(script, /param\(\[Parameter\(Mandatory = \$true\)\]\[string\[\]\]\$Arguments\)/);
  assert.doesNotMatch(script, /Invoke-Wsl\s+(?:mkdir|git|sudo|wslpath|sh)\b/);
  assert.match(script, /Invoke-Wsl -Arguments @\("mkdir", "-p", \$destinationRootLinux\)/);
  assert.match(script, /Invoke-Wsl -Arguments @\("git", "-C", \$destinationLinux/);

  // Drive-letter Windows paths are converted without routing through shell parsing that can
  // consume backslashes (for example D:\\Projects\\repo -> /mnt/d/Projects/repo).
  assert.match(script, /\^\(\[A-Za-z\]\):\\\\\(\.\*\)\$/);
  assert.match(script, /return "\/mnt\/\$drive\/\$rest"/);
  assert.doesNotMatch(script, /Invoke-Wsl[^\n]*wslpath/);

  // A failed WSL HOME lookup must fail closed instead of silently producing /projects.
  assert.match(script, /if \(-not \$wslHome\)/);
  assert.match(script, /Could not resolve the WSL home directory/);
});

test('Windows WSL2 guide documents safe default and rollback', async () => {
  const guide = await text('docs/WINDOWS_WSL2.md');
  assert.match(guide, /defaults Windows development to WSL2/i);
  assert.match(guide, /~\/projects/);
  assert.match(guide, /Do not install a second Docker Engine inside WSL/i);
  assert.match(guide, /does \*\*not\*\* delete the Windows source checkout/i);
  assert.match(guide, /Rollback/);
});
