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

test('publication optionally includes exact Auth Kit only when the package declares it', () => {
  const workflow = fs.readFileSync(WORKFLOW, 'utf8').replace(/\r\n/g, '\n');
  const pins = extractRunBlock(workflow, 'Resolve exact component pins');
  const sources = extractRunBlock(workflow, 'Resolve protected source repositories');
  const checkouts = extractRunBlock(workflow, 'Verify exact private source checkouts');
  const release = extractRunBlock(workflow, 'Prepare reproducible release candidate');

  assert.match(pins, /Object\.keys\(data\.components \?\? \{\}\)\.sort\(\)/);
  assert.match(pins, /ids\.includes\('authentication'\)/);
  assert.match(pins, /only complete Core \+ Deployment and optional Authentication/);
  assert.match(pins, /invalid \$\{id\} revision/);

  assert.match(workflow, /secrets\.AUTHENTICATION_SOURCE_REPOSITORY/);
  assert.match(workflow, /steps\.pins\.outputs\.authentication/);
  assert.match(sources, /check_mapping AUTHENTICATION_SOURCE_REPOSITORY/);
  assert.match(sources, /authentication=\$AUTHENTICATION_SOURCE_REPOSITORY/);
  assert.match(workflow, /- name: Checkout exact Authentication source only when advertised\n\s+if: steps\.pins\.outputs\.authentication != ''/);
  assert.match(workflow, /ref: \$\{\{ steps\.pins\.outputs\.authentication \}\}/);
  assert.match(workflow, /path: \.release-sources\/authentication/);
  assert.match(checkouts, /verify_checkout \.release-sources\/authentication "\$AUTHENTICATION_REVISION"/);
  assert.match(release, /args\+=\(--authentication-root \.release-sources\/authentication\)/);
  assert.match(release, /node scripts\/prepare-release\.mjs "\$\{args\[@\]\}"/);

  // Retain clean, reproducible two-component publication for existing releases.
  assert.match(release, /if \[\[ -n "\$AUTHENTICATION_REVISION" \]\]/);
  assert.doesNotMatch(workflow, /mriekki\/project-forge-auth-kit/);
  if (process.platform !== 'win32') {
    for (const script of [pins, sources, checkouts, release]) {
      // Each block contains either shell commands or the existing Node heredoc;
      // Bash syntax validation is valid for both forms.
      execFileSync('bash', ['-n'], { input: script, encoding: 'utf8' });
    }
  }
});

test('publication binds optional Feedback to exact source and protected mapping', () => {
  const workflow = fs.readFileSync(WORKFLOW, 'utf8');
  const pins = extractRunBlock(workflow, 'Resolve exact component pins');
  const sources = extractRunBlock(workflow, 'Resolve protected source repositories');
  const checkouts = extractRunBlock(workflow, 'Verify exact private source checkouts');
  const release = extractRunBlock(workflow, 'Prepare reproducible release candidate');
  assert.match(pins, /ids\.includes\('feedback'\)/);
  assert.match(sources, /check_mapping FEEDBACK_SOURCE_REPOSITORY/);
  assert.match(workflow, /secrets\.FEEDBACK_SOURCE_REPOSITORY/);
  assert.match(workflow, /steps\.pins\.outputs\.feedback/);
  assert.match(checkouts, /verify_checkout \.release-sources\/feedback "\$FEEDBACK_REVISION"/);
  assert.match(release, /args\+=\(--feedback-root \.release-sources\/feedback\)/);
});
