/** Bounded JSON with decoded-name duplicate rejection, including nested objects. */
export function strictJson(raw,max=1024*1024){
 if(typeof raw!=='string'||Buffer.byteLength(raw)>max)throw Error('Invalid bounded JSON');
 let i=0;
 const ws=()=>{while(/[\x20\t\r\n]/.test(raw[i]??''))i++;};
 function string(){
  const start=i++;
  while(i<raw.length){
   if(raw[i]==='\\'){i+=2;continue;}
   if(raw[i++]==='"')return JSON.parse(raw.slice(start,i));
  }
  throw Error('Unterminated JSON string');
 }
 function value(depth){
  if(depth>64)throw Error('JSON nesting limit');
  ws();
  if(raw[i]==='{'){
   i++;ws();const keys=new Set();
   if(raw[i]==='}'){i++;return;}
   for(;;){
    ws();if(raw[i]!=='"')throw Error('Invalid JSON key');
    const k=string();if(keys.has(k))throw Error('Duplicate JSON field');keys.add(k);
    ws();if(raw[i++]!==':')throw Error('Invalid JSON separator');
    value(depth+1);ws();const c=raw[i++];
    if(c==='}')return;if(c!==',')throw Error('Invalid JSON object');
   }
  }
  if(raw[i]==='['){
   i++;ws();if(raw[i]===']'){i++;return;}
   for(;;){value(depth+1);ws();const c=raw[i++];if(c===']')return;if(c!==',')throw Error('Invalid JSON array');}
  }
  if(raw[i]==='"'){string();return;}
  const start=i;
  while(i<raw.length&&!/[\x20\t\r\n,}\]]/.test(raw[i]))i++;
  if(i===start)throw Error('Invalid JSON value');JSON.parse(raw.slice(start,i));
 }
 value(0);ws();if(i!==raw.length)throw Error('Trailing JSON input');
 return JSON.parse(raw);
}
