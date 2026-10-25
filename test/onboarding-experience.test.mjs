import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

async function text(path) {
  return readFile(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('welcome page leads with the approved static infographic without duplicating the lifecycle Mermaid', async () => {
  const welcome = await text('WELCOME.md');
  const imageMarkdown = '![Project Forge overview showing the journey from an idea through planning, GitHub repository generation, AI-assisted development, delivery, learning, and controlled deployment.](./docs/images/project-forge-welcome.jpg)';
  const imageIndex = welcome.indexOf(imageMarkdown);
  const mermaidCount = (welcome.match(/```mermaid/g) || []).length;

  assert.ok(imageIndex >= 0, 'WELCOME.md must use the approved relative Markdown image reference');
  assert.doesNotMatch(welcome, /<img\b/i, 'WELCOME.md should not use raw HTML for the welcome infographic');
  assert.equal(mermaidCount, 1, 'WELCOME.md should keep only the non-duplicative human-control Mermaid');
  assert.match(welcome, /AI handles mechanics; humans retain engineering authority/);
  assert.doesNotMatch(welcome, /Project Forge at a glance/);
  assert.doesNotMatch(welcome, /project-forge-overview\.svg/);
  assert.doesNotMatch(welcome, /\bMark\b|\bKyle\b/);
  assert.doesNotMatch(welcome, /\b[a-f0-9]{40}\b/i);
  assert.doesNotMatch(welcome, /sourceProvenance/);
});

test('ChatGPT setup converges every Builder on one canonical instruction plus personal profile', async () => {
  const setup = await text('chatgpt/SETUP.md');

  assert.match(setup, /same for every Builder/i);
  assert.match(setup, /same for every Project Forge Builder/);
  assert.match(setup, /Project Forge Developer Profile/);
  assert.match(setup, /Verify my Project Forge setup\./);
  assert.match(setup, /README welcome page/);
  assert.match(setup, /do \*\*not\*\* copy .*handoff/i);
  assert.doesNotMatch(setup, /\bMark\b|\bKyle\b/);
  assert.doesNotMatch(setup, /\b[a-f0-9]{40}\b/i);
  assert.doesNotMatch(setup, /sourceProvenance/);
});
