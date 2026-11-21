#!/usr/bin/env node
// Parse strictly owner-authored, nonpublishing GitHub Issue requests to start
// the EXISTING private-source read-only admission preview (no new token/job).
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const ISSUE_TITLE = '[project-forge-source-preview]';
const SHA40 = /^[0-9a-f]{40}$/;
const MODES = new Set(['historical-4.35', 'changed-feedback-4.36-preview']);

function requireThat(value, reason) {
  if (!value) throw new Error(reason);
}

export function resolvePreviewTrigger({ eventName, dispatch, event, repositoryOwner }) {
  let values;
  if (eventName === 'workflow_dispatch') {
    values = {
      sourceSha: dispatch?.exact_source_sha,
      sourceRunId: dispatch?.source_qualification_run_id,
      candidateMode: dispatch?.candidate_mode ?? 'historical-4.35'
    };
  } else if (eventName === 'issues') {
    requireThat(typeof repositoryOwner === 'string' && repositoryOwner.length > 0 &&
      event?.action === 'opened' && event?.issue?.title === ISSUE_TITLE &&
      event?.issue?.user?.login === repositoryOwner &&
      event?.sender?.login === repositoryOwner &&
      event?.issue?.state === 'open',
    'Only a newly opened, owner-authored exact preview request is allowed');
    try {
      values = JSON.parse(event.issue.body);
    } catch {
      throw new Error('Preview request body must be exact JSON');
    }
    requireThat(values && typeof values === 'object' && !Array.isArray(values) &&
      JSON.stringify(Object.keys(values).sort()) ===
        JSON.stringify(['candidateMode', 'sourceRunId', 'sourceSha']),
    'Preview issue body must contain exactly sourceSha, sourceRunId, candidateMode');
  } else {
    throw new Error('Unsupported preview request event');
  }
  requireThat(typeof values.sourceSha === 'string' && SHA40.test(values.sourceSha),
    'Preview source commit must be exact immutable SHA');
  const runId = typeof values.sourceRunId === 'string'
    ? (/^[1-9][0-9]*$/.test(values.sourceRunId)
        ? Number(values.sourceRunId) : NaN)
    : values.sourceRunId;
  requireThat(Number.isSafeInteger(runId) && runId > 0,
    'Preview requires an exact positive source qualification run ID');
  requireThat(MODES.has(values.candidateMode), 'Unsupported or publishing preview mode');
  return Object.freeze({
    sourceSha: values.sourceSha, sourceRunId: runId, candidateMode: values.candidateMode
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const eventName = process.env.PF_EVENT_NAME;
    const dispatch = {
      exact_source_sha: process.env.PF_DISPATCH_SHA,
      source_qualification_run_id: process.env.PF_DISPATCH_RUN,
      candidate_mode: process.env.PF_DISPATCH_MODE
    };
    const event = eventName === 'issues'
      ? JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'))
      : null;
    const request = resolvePreviewTrigger({
      eventName, dispatch, event, repositoryOwner: process.env.PF_REPOSITORY_OWNER
    });
    fs.appendFileSync(process.env.GITHUB_OUTPUT,
      'source_sha=' + request.sourceSha + '\n' +
      'source_run_id=' + request.sourceRunId + '\n' +
      'candidate_mode=' + request.candidateMode + '\n');
    console.log('Validated exact owner-authorized read-only preview request');
  } catch (error) {
    console.error('Public read-only preview request refused: ' + error.message);
    process.exitCode = 2;
  }
}
