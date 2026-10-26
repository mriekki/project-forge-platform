import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

async function text(path) {
  return readFile(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('welcome page leads with a renderer-native infographic and has no static image dependency', async () => {
  const welcome = await text('WELCOME.md');
  const overviewHeading = '## Project Forge at a glance';
  const headingIndex = welcome.indexOf(overviewHeading);
  const firstMermaidIndex = welcome.indexOf('```mermaid');
  const descriptionIndex = welcome.indexOf('Project Forge is an AI-guided software development and learning platform');
  const mermaidBlocks = welcome.match(/```mermaid[\s\S]*?```/g) || [];

  assert.ok(headingIndex >= 0, 'WELCOME.md must lead with the Project Forge at-a-glance infographic');
  assert.ok(firstMermaidIndex > headingIndex, 'the at-a-glance infographic must be Mermaid source after its heading');
  assert.ok(descriptionIndex > firstMermaidIndex, 'the renderer-native infographic must appear before the prose introduction');
  assert.equal(mermaidBlocks.length, 2, 'WELCOME.md should contain the at-a-glance and human-control Mermaid diagrams');

  for (const required of [
    'Idea',
    'Guided discovery',
    'PROJECT_BOOTSTRAP.json',
    'Setup',
    'Build',
    'Review + deliver',
    'Learn',
    'Deploy',
  ]) {
    assert.match(mermaidBlocks[0], new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }

  assert.doesNotMatch(welcome, /!\[[^\]]*\]\([^)]*\)/, 'WELCOME.md must not depend on a static Markdown image for the infographic');
  assert.doesNotMatch(welcome, /<img\b/i, 'WELCOME.md must not depend on raw HTML images for the infographic');
  assert.doesNotMatch(welcome, /project-forge-welcome\.(?:jpg|jpeg|png|webp|svg)/i);
  assert.match(welcome, /AI handles mechanics; humans retain engineering authority/);
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
