import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function text(relative) {
  return readFile(path.join(root, relative), 'utf8');
}

test('stable ChatGPT instruction requires granular existing-repository adoption review', async () => {
  const descriptor = JSON.parse(await text('chatgpt/current.json'));
  const instructions = await text(`${descriptor.snapshotPath}/PROJECT_INSTRUCTIONS.md`);

  assert.match(instructions, /complete repository archaeology before asking disposition questions/i);
  assert.match(instructions, /one meaningful material decision at a time/i);
  assert.match(instructions, /exact asset\/topic/i);
  assert.match(instructions, /evidence-backed recommendation/i);
  assert.match(instructions, /free-form option/i);
  assert.match(instructions, /AI\/agentic assets individually/i);
  assert.match(instructions, /Do not manufacture questions for mechanical facts/i);
  assert.match(instructions, /how many meaningful decisions remain/i);
  assert.match(instructions, /exact final reconciliation/i);
  assert.match(instructions, /Apply adoption \[WRITE\]\?/);
  assert.match(instructions, /exact analyzed repository snapshot/i);
});
