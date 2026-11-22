/** Nonpublishing PR CI gate for newly introduced immutable native selections.
 * Check the literal head commit, never the synthetic PR merge tree. The release
 * publisher remains the only authority allowed to consume or publish.
 */
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {strictJson} from './strict-json.mjs';
import {validateSelection} from './native-successor-publication.mjs';

const SHA=/^[0-9a-f]{40}$/;
const PREFIX='release/native-selections/';
const need=(ok,msg)=>{if(!ok)throw new Error(msg);};

export function verifyOneIntroducedSelection({status,file,bytes,historyCount}) {
 need(typeof file==='string'&&file.startsWith(PREFIX)&&file.endsWith('.json')&&
  !file.slice(PREFIX.length).includes('/'),'Unexpected native selection path');
 need(status==='A','Immutable release selection edited, deleted or replaced: '+file);
 need(Number.isSafeInteger(historyCount)&&historyCount===1,
  'Native selection must have exactly one introducing commit: '+file);
 need(typeof bytes==='string'&&Buffer.byteLength(bytes)>0&&Buffer.byteLength(bytes)<=65536,
  'Invalid bounded selection payload');
 const selected=validateSelection(strictJson(bytes,65536));
 need(file===PREFIX+selected.source.version+'.json','Native selection path/version mismatch');
 return {version:selected.source.version,sha256:createHash('sha256').update(bytes).digest('hex')};
}

export function validateSelectionDelta({diff,readFile,historyCount}) {
 need(typeof diff==='string'&&Buffer.byteLength(diff)<=65536,'Bounded PR selection delta required');
 const reports=[];
 for(const line of diff.split('\n').filter(Boolean)){
  const match=/^([A-Z]+)\t([^\t\n]+)$/.exec(line);
  need(match,'Malformed git path status in native selection delta');
  const [,status,file]=match;
  if(!file.startsWith(PREFIX))continue;
  // JSON names under the protected directory are always part of the one-use authority.
  need(file.endsWith('.json'),'Unexpected non-JSON change in native selection directory');
  reports.push(verifyOneIntroducedSelection({
   status,file,bytes:readFile(file),historyCount:historyCount(file)}));
 }
 return reports;
}

function git(args){
 return execFileSync('git',args,{encoding:'utf8',timeout:30000,maxBuffer:1024*1024});
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const base=process.env.PR_BASE_SHA,head=process.env.PR_HEAD_SHA;
  need(SHA.test(base)&&SHA.test(head)&&base!==head,'Exact PR base/head required');
  const reports=validateSelectionDelta({
   diff:git(['diff','--name-status','--no-renames',base,head,'--',PREFIX]),
   readFile:file=>git(['show',head+':'+file]),
   historyCount:file=>Number(git(['rev-list','--count',head,'--',file]).trim())
  });
  for(const r of reports)console.log('PASS new one-commit native selection '+r.version+' sha256 '+r.sha256);
  console.log('PASS newly introduced immutable native release selections qualified (NO PUBLISH)');
 }catch(e){
  console.error('Native selection PR CI refused: '+e.message);
  process.exitCode=2;
 }
}
