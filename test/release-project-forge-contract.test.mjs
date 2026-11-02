import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');

function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('package release supports end-to-end authorization with exact stable ChatGPT contract follow-up', () => {
  const skill = read('.github/skills/release-project-forge/SKILL.md');

  assert.match(skill, /End-to-end release authorization/);
  assert.match(skill, /single bounded approval/i);
  assert.match(skill, /Do not ask for repeated ceremonial confirmations/i);
  assert.match(skill, /After successful publication, inspect live `chatgpt\/current\.json`/i);
  assert.match(skill, /compare `generation\.package` \/ `generation\.packageVersion` plus the accepted Bootstrap revision\/compatibility/i);
  assert.match(skill, /Never point stable at an unpublished package/i);
  assert.match(skill, /Never edit a published immutable snapshot in place/i);
  assert.match(skill, /merge the unchanged reviewed head automatically/i);
  assert.match(skill, /granular authorization.*normal human merge\/finalize gate/is);
  assert.match(skill, /Public ChatGPT contract: ALIGNED/);
});
