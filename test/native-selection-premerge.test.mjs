import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyOneIntroducedSelection,validateSelectionDelta} from '../scripts/validate-native-selection-pr.mjs';

const SOURCE='a'.repeat(40), PREVIEW='b'.repeat(40), PRIOR='c'.repeat(64);
const MANIFEST='d'.repeat(64),CANDIDATE='e'.repeat(64);
const FILE='release/native-selections/4.36.2.json';
const selection=()=>({
 schemaVersion:1,kind:'project-forge-reviewed-native-successor-selection',
 source:{sourceCommit:SOURCE,workflowRunId:10,runAttempt:1,
  previousVersion:'4.36.0',previousReceiptSha256:PRIOR,
  version:'4.36.2',manifestSha256:MANIFEST,candidateSha256:CANDIDATE},
 preview:{platformCommit:PREVIEW,workflowId:42,runId:43,runAttempt:1},
 authorization:{issueNumber:417,issueId:6546751036}
});
const check=(sel=selection(),opts={})=>verifyOneIntroducedSelection({
 status:opts.status??'A',file:opts.file??FILE,historyCount:opts.historyCount??1,
 bytes:opts.bytes??JSON.stringify(sel)+'\n'});

test('one brand-new owner-bound selection with exact 64-hex digests qualifies',()=>{
 const x=check();
 assert.equal(x.version,'4.36.2');
 assert.match(x.sha256,/^[0-9a-f]{64}$/);
});
test('regression: 61-hex truncated candidate digest is refused before PR merge',()=>{
 assert.throws(()=>check({...selection(),source:{...selection().source,candidateSha256:
  '699abf7b5071a34247847d9ea40a9048a8cbe4eebe3d9558a6648612ec852'}}),
  /Invalid stable successor selection/);
});
test('malformed predecessor digest, invalid owner ID or mismatched path fails closed',()=>{
 assert.throws(()=>check({...selection(),source:{...selection().source,previousReceiptSha256:'f'.repeat(61)}}),
  /Invalid stable successor selection/);
 assert.throws(()=>check({...selection(),authorization:{issueNumber:417,issueId:0}}),
  /Exact authorization issue identity/);
 assert.throws(()=>check(selection(),{file:'release/native-selections/4.36.1.json'}),
  /path\/version mismatch/);
});
test('immutable paths cannot be edited, deleted, renamed/reintroduced or added twice',()=>{
 for(const status of ['M','D','R100'])
  assert.throws(()=>check(selection(),{status}),/Immutable release selection/);
 assert.throws(()=>check(selection(),{historyCount:2}),/exactly one introducing commit/);
 assert.throws(()=>check(selection(),{file:'release/native-selections/nested/4.36.2.json'}),/Unexpected native selection path/);
});
test('source and admission selection field schemas are exact and strict JSON',()=>{
 const x=selection();
 assert.throws(()=>check({...x,source:{...x.source,extra:'unapproved'}}),/Invalid source selection/);
 assert.throws(()=>check(selection(),{bytes:'{"version":1,"version":2}\n'}));
});
test('delta gate reads only newly added native selections from the PR exact head',()=>{
 const seen=[];
 const reports=validateSelectionDelta({
  diff:'A\t'+FILE+'\n',
  readFile:file=>{seen.push(file);return JSON.stringify(selection())+'\n';},
  historyCount:()=>1
 });
 assert.equal(reports.length,1);assert.deepEqual(seen,[FILE]);
 assert.deepEqual(validateSelectionDelta({diff:'',readFile:()=>{throw Error('unexpected')},historyCount:()=>0}),[]);
 assert.throws(()=>validateSelectionDelta({diff:'M\t'+FILE+'\n',
  readFile:()=>JSON.stringify(selection()),historyCount:()=>1}),/Immutable release selection/);
});
