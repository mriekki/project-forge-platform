import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

async function text(path) {
  return readFile(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('welcome page leads with a static visual lifecycle infographic', async () => {
  const welcome = await text('WELCOME.md');
  const svg = await text('docs/images/project-forge-overview.svg');
  const imageIndex = welcome.indexOf('docs/images/project-forge-overview.svg');
  const mermaidIndex = welcome.indexOf('```mermaid');

  assert.ok(imageIndex >= 0, 'WELCOME.md must reference the static infographic');
  assert.ok(mermaidIndex > imageIndex, 'static infographic must appear before Mermaid');
  assert.match(svg, /Project Forge lifecycle overview/);
  assert.match(svg, /HUMAN CONTROL/);
  assert.match(svg, /DEPLOY WHEN READY/);
});

test('ChatGPT setup converges every Builder on one canonical instruction plus personal profile', async () => {
  const setup = await text('chatgpt/SETUP.md');

  assert.match(setup, /same for every Builder/i);
  assert.match(setup, /same for Mark, Kyle, and every other Project Forge Builder/);
  assert.match(setup, /Project Forge Developer Profile/);
  assert.match(setup, /Verify my Project Forge setup\./);
  assert.match(setup, /README welcome page/);
  assert.doesNotMatch(setup, /copy .*handoff/i);
});
