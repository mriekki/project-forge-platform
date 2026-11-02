import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WORKFLOW = path.join(ROOT, '.github', 'workflows', 'npm-publish.yml');

function extractRunBlock(rawWorkflow, stepName) {
  const workflow = rawWorkflow.replace(/\r\n/g, '\n');
  const stepMarker = `      - name: ${stepName}\n`;
  const stepStart = workflow.indexOf(stepMarker);
  assert.notEqual(stepStart, -1, `missing workflow step: ${stepName}`);

  const runMarker = '        run: |\n';
  const runStart = workflow.indexOf(runMarker, stepStart);
  assert.notEqual(runStart, -1, `missing run block: ${stepName}`);

  const bodyStart = runStart + runMarker.length;
  const nextStep = workflow.indexOf('\n      - name:', bodyStart);
  const raw = workflow.slice(bodyStart, nextStep === -1 ? workflow.length : nextStep);
  return raw
    .split('\n')
    .map((line) => line.startsWith('          ') ? line.slice(10) : line)
    .join('\n');
}

test('publication recovery source guard is valid Bash and avoids nested heredoc indentation', () => {
  const workflow = fs.readFileSync(WORKFLOW, 'utf8');
  const script = extractRunBlock(workflow, 'Verify authorized Project Forge Platform source');

  assert.match(script, /check-package-release-drift\.mjs --baseline/);
  assert.match(script, /node -e 'const fs=require\("node:fs"\)/);
  assert.doesNotMatch(script, /node <<'NODE'/);

  if (process.platform !== 'win32') {
    execFileSync('bash', ['-n'], { input: script, encoding: 'utf8' });
  }
});
