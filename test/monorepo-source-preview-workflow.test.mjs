import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const preview = fs.readFileSync(path.join(ROOT, '.github/workflows/p0-monorepo-source-preview.yml'), 'utf8');
const publish = fs.readFileSync(path.join(ROOT, '.github/workflows/npm-publish.yml'), 'utf8');

test('public/private source preview accepts only manual or owner-Issue requests behind protected variable', () => {
  assert.match(preview, /^\s*workflow_dispatch:/m);
  assert.match(preview, /^\s*issues:/m);
  assert.match(preview, /types: \[opened\]/);
  assert.match(preview, /github\.event\.issue\.user\.login == github\.repository_owner/);
  assert.match(preview, /github\.event\.sender\.login == github\.repository_owner/);
  assert.match(preview, /github\.event\.issue\.title == '\[project-forge-source-preview\]'/);
  assert.doesNotMatch(preview, /^\s*pull_request:/m);
  assert.doesNotMatch(preview, /^\s*push:/m);
  assert.match(preview, /vars\.PF_MONOREPO_SOURCE_PREVIEW_ENABLED == 'true'/);
  assert.match(preview, /github\.ref == 'refs\/heads\/main'/);
  assert.match(preview, /github\.repository == 'mriekki\/project-forge-platform'/);
});

test('private source mapping and immutable repo ID are protected, run evidence is authenticated', () => {
  assert.match(preview, /secrets\.PF_MONOREPO_SOURCE_REPOSITORY/);
  assert.match(preview, /secrets\.PF_MONOREPO_SOURCE_REPOSITORY_ID/);
  assert.match(preview, /secrets\.PF_MONOREPO_SOURCE_READ_TOKEN/);
  assert.match(preview, /actions\/runs\/\$SOURCE_RUN/);
  assert.match(preview, /private-source-admission-preview\.mjs/);
  assert.match(preview, /--source-sha "\$EXPECTED_SHA"/);
  assert.match(preview, /--source-run-id "\$SOURCE_RUN"/);
});

test('preview independently rebuilds source and compares a historical public receipt', () => {
  assert.match(preview, /repository: \$\{\{ steps\.evidence\.outputs\.repository \}\}/);
  assert.match(preview, /ref: \$\{\{ steps\.request\.outputs\.source_sha \}\}/);
  assert.match(preview, /persist-credentials: false/g);
  assert.match(preview, /build_candidate\.py/);
  assert.match(preview, /candidate_handoff\.py emit/);
  assert.match(preview, /verify-candidate-handoff\.mjs/);
  assert.match(preview, /--package-version 4\.35\.0/);
  assert.match(preview, /Private main advanced during preview/);
});

test('changed-source mode requires completed optional proof, not just a selected mode', () => {
  assert.ok(preview.includes("id: changed_preview"));
  assert.ok(preview.includes("if: steps.request.outputs.candidate_mode == 'changed-feedback-4.36-preview'"));
  assert.ok(!preview.includes("if: inputs.candidate_mode =="));
  assert.ok(preview.includes(`echo 'verified=true' >> "$GITHUB_OUTPUT"`));
  assert.ok(preview.includes("steps.changed_preview.outputs.verified"));
  assert.ok(preview.includes("Changed-source verification step did not complete successfully"));
});

test('legacy public npm publisher remains untouched and preview has no publish or elevated token scope', () => {
  assert.match(preview, /permissions:\n  contents: read/);
  assert.doesNotMatch(preview, /npm publish\s/);
  assert.doesNotMatch(preview, /id-token: write|contents: write|actions: write/);
  assert.doesNotMatch(preview, /upload-artifact/);
  assert.match(preview, /NPM_PUBLISHED=false/);
  assert.match(preview, /RELEASE_AUTHORIZED=false/);
  assert.match(publish, /npm publish "dist\/release\/\$\{TARBALL\}"/);
  assert.match(publish, /secrets\.PROJECT_FORGE_SOURCE_TOKEN/);
  assert.doesNotMatch(publish, /secrets\.PF_MONOREPO_SOURCE_READ_TOKEN/);
  assert.doesNotMatch(preview, /secrets\.PROJECT_FORGE_SOURCE_TOKEN/);
  assert.doesNotMatch(publish, /private-source-admission-preview/);
});
