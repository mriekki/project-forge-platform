#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, html, json, os, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IGNORE={".git","node_modules","bin","obj","dist","build","target",".venv","venv","__pycache__","coverage",".next"}
MANIFEST={"package.json","pyproject.toml","pom.xml","build.gradle","build.gradle.kts","go.mod"}
EXT={".cs",".java",".kt",".py",".js",".jsx",".ts",".tsx",".go",".json",".toml",".xml",".yml",".yaml"}
DB={"sqlite":(r"UseSqlite",r"Microsoft\.Data\.Sqlite",r"\bsqlite3?\b"),"postgresql":(r"UseNpgsql",r"\bNpgsql",r"\bpostgres(?:ql)?\b"),"sqlserver":(r"UseSqlServer",r"\bSqlClient",r"SQL Server"),"mysql":(r"UseMySql",r"MySqlConnector",r"\bmysql\b")}
MSG={"kafka":(r"\bKafka\b",),"rabbitmq":(r"RabbitMQ",),"servicebus":(r"ServiceBus",),"sqs":(r"\bSQS",),"masstransit":(r"MassTransit",)}
ROUTES=(re.compile(r'Map(?P<m>Get|Post|Put|Delete|Patch)\s*\(\s*"(?P<r>[^"]+)"'),re.compile(r'@(?:app|router)\.(?P<m>get|post|put|delete|patch)\s*\(\s*["\'](?P<r>[^"\']+)'))

def slug(v:str)->str: return re.sub(r"[^A-Za-z0-9]+","-",v).strip("-").lower() or "component"
def rel(repo:Path,p:Path)->str:
    try:return p.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:return p.as_posix()
def read(p:Path)->str:
    try:
        if p.stat().st_size>750_000:return ""
        return p.read_text(encoding="utf-8",errors="ignore")
    except OSError:return ""
def match(text:str,pats:tuple[str,...])->bool:return any(re.search(p,text,re.I) for p in pats)
def ev(path:str,reason:str,label:str="CONFIRMED BY CODE")->dict[str,str]:return {"label":label,"path":path,"reason":reason}
def unique(xs:list[Any],v:Any)->None:
    if v not in xs:xs.append(v)
def sha(v:Any)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def git(repo:Path,*args:str)->str|None:
    try:r=subprocess.run(["git","-C",str(repo),*args],text=True,capture_output=True,timeout=5)
    except (OSError,subprocess.SubprocessError):return None
    return r.stdout.strip() if r.returncode==0 and r.stdout.strip() else None

def files(repo:Path)->list[Path]:
    out=[]
    for root,dirs,names in os.walk(repo):
        dirs[:]=[d for d in dirs if d not in IGNORE]
        for n in names:
            p=Path(root)/n
            if p.suffix.lower() in EXT or n in MANIFEST or n.endswith(".csproj") or n in {"Dockerfile","docker-compose.yml","docker-compose.yaml","compose.yml","compose.yaml"}:out.append(p)
    return out

def component(cid:str,name:str,kind:str,path:str,evidence:dict[str,str])->dict[str,Any]:
    return {"id":cid,"name":name,"kind":kind,"path":path,"responsibilities":[],"interfaces":[],"state":[],"scaling":[],"failureModes":[],"telemetry":[],"security":[],"deployment":[],"tests":[],"evidence":[evidence],"changeState":"unchanged","changedFiles":[]}

def roots(repo:Path,fs:list[Path])->dict[str,dict[str,Any]]:
    out={}
    for p in fs:
        if p.name not in MANIFEST and p.suffix!=".csproj":continue
        text=read(p); root=p.parent; rr=rel(repo,root); name=p.stem if p.suffix==".csproj" else root.name or repo.name
        if p.name=="package.json":
            try:name=str(json.loads(text).get("name") or name)
            except json.JSONDecodeError:pass
        lower=text.lower(); kind="application"
        if p.name=="package.json" and any(x in lower for x in ("react","next","@angular/core","vue","svelte")):kind="frontend"
        elif any(x in lower for x in ("microsoft.net.sdk.web","aspnetcore","spring-boot","fastapi","django","flask","express","fastify","@nestjs/core")):kind="service"
        cid=slug(rr if rr not in {"","."} else name)
        if cid in out:out[cid]["evidence"].append(ev(rel(repo,p),"project/package manifest"))
        else:out[cid]=component(cid,name,kind,rr,ev(rel(repo,p),"project/package manifest"))
    if not out:out["repo"]=component("repo",repo.name,"application",".",ev(".","repository root fallback","INFERRED"))
    return out

def owner(repo:Path,p:Path,cs:dict[str,dict[str,Any]])->str|None:
    rp=rel(repo,p); hits=[]
    for cid,c in cs.items():
        root=str(c.get("path") or ".").rstrip("/")
        if root in {"",".","(logical)","(compose)"}:
            if root in {"","."}:hits.append((0,cid))
        elif rp==root or rp.startswith(root+"/"):hits.append((len(root),cid))
    return max(hits)[1] if hits else None

def dep(cs:dict[str,dict[str,Any]],kind:str,key:str,name:str,evidence:dict[str,str])->str:
    aliases={key.lower(),"postgres" if key=="postgresql" else key.lower(),"mssql" if key=="sqlserver" else key.lower()}
    for cid,c in cs.items():
        if c["kind"]!=kind:continue
        hay=(" ".join([c["name"],c["path"]]+[str(x) for x in c["state"]])).lower()
        if any(a in hay for a in aliases):c["evidence"].append(evidence);return cid
    cid=slug(f"{kind}-{key}")
    if cid not in cs:
        cs[cid]=component(cid,name,kind,"(logical)",evidence);cs[cid]["evidence"][0]["label"]="INFERRED"
    else:cs[cid]["evidence"].append(evidence)
    return cid

def add_edge(es:dict[str,dict[str,Any]],a:str,b:str,kind:str,protocol:str,evidence:dict[str,str],async_:bool=False)->None:
    eid=slug(f"{a}-{kind}-{b}")
    if eid not in es:es[eid]={"id":eid,"from":a,"to":b,"kind":kind,"protocol":protocol,"asynchronous":async_,"timeout":"UNKNOWN","retry":"UNKNOWN","evidence":[evidence],"changeState":"unchanged"}
    else:es[eid]["evidence"].append(evidence)

def compose(repo:Path,fs:list[Path],cs:dict[str,dict[str,Any]],es:dict[str,dict[str,Any]])->None:
    names={"docker-compose.yml","docker-compose.yaml","compose.yml","compose.yaml"}
    for p in fs:
        if p.name not in names:continue
        active=False;cur=None;in_dep=False;ids={};rp=rel(repo,p)
        for raw in read(p).splitlines():
            s=raw.strip(); ind=len(raw)-len(raw.lstrip(" "))
            if not s or s.startswith("#"):continue
            if ind==0 and s=="services:":active=True;continue
            if ind==0 and s.endswith(":") and s!="services:":active=False;cur=None
            if not active:continue
            if ind==2 and s.endswith(":"):
                cur=s[:-1].strip();in_dep=False;cid=next((k for k,c in cs.items() if c["name"].lower()==cur.lower()),slug("compose-"+cur))
                if cid not in cs:cs[cid]=component(cid,cur,"service","(compose)",ev(rp,f"Compose service {cur}"))
                else:cs[cid]["evidence"].append(ev(rp,f"Compose service {cur}"))
                ids[cur]=cid;unique(cs[cid]["deployment"],f"Compose service: {cur}");continue
            if not cur:continue
            if ind==4 and s.startswith("image:"):
                image=s.split(":",1)[1].strip().lower();cid=ids[cur]
                if any(x in image for x in ("postgres","mysql","mariadb","mssql","sqlserver")):cs[cid]["kind"]="database"
                elif "redis" in image:cs[cid]["kind"]="cache"
                elif any(x in image for x in ("rabbitmq","kafka","redpanda")):cs[cid]["kind"]="messaging"
                unique(cs[cid]["state"],f"Compose image: {image}");continue
            if ind==4 and s.startswith("depends_on:"):in_dep=True;continue
            if ind==4 and s.endswith(":"):in_dep=False
            if in_dep and ind>=6:
                d=s.lstrip("- ").split(":",1)[0].strip()
                if d:
                    target=ids.get(d,slug("compose-"+d))
                    if target not in cs:cs[target]=component(target,d,"service","(compose)",ev(rp,f"Compose dependency {d}","INFERRED"))
                    ids[d]=target;add_edge(es,ids[cur],target,"dependency","Compose",ev(rp,f"{cur} depends_on {d}"))

def scan(repo:Path,fs:list[Path],cs:dict[str,dict[str,Any]],es:dict[str,dict[str,Any]])->None:
    for p in fs:
        if p.name in {"docker-compose.yml","docker-compose.yaml","compose.yml","compose.yaml"}:continue
        text=read(p);own=owner(repo,p,cs)
        if not text or not own:continue
        c=cs[own];rp=rel(repo,p)
        if match(text,(r"\[ApiController\]",r"Map(?:Get|Post|Put|Delete|Patch)\s*\(",r"FastAPI\s*\(",r"@RequestMapping",r"@(?:app|router)\.(?:get|post|put|delete|patch)")):
            unique(c["responsibilities"],"Exposes application/API entry points");c["evidence"].append(ev(rp,"API/framework signal"))
        for pat in ROUTES:
            for m in pat.finditer(text):unique(c["interfaces"],f"{m.group('m').replace('Http','').upper()} {m.group('r')}")
        for key,pats in DB.items():
            if match(text,pats):
                t=dep(cs,"database",key,"PostgreSQL" if key=="postgresql" else key.upper(),ev(rp,f"{key} persistence signal","INFERRED"))
                add_edge(es,own,t,"data","SQL",ev(rp,f"{key} persistence reference","INFERRED"));unique(c["state"],f"Uses {cs[t]['name']} persistence")
        if match(text,(r"\bRedis\b",r"StackExchange\.Redis",r"\bioredis\b")):
            t=dep(cs,"cache","redis","Redis",ev(rp,"Redis cache signal","INFERRED"));add_edge(es,own,t,"cache","Redis",ev(rp,"Redis reference","INFERRED"));unique(c["failureModes"],"Cache unavailability/staleness may matter")
        for key,pats in MSG.items():
            if match(text,pats):
                t=dep(cs,"messaging",key,key,ev(rp,f"{key} messaging signal","INFERRED"));add_edge(es,own,t,"message",key,ev(rp,f"{key} reference","INFERRED"),True);unique(c["failureModes"],"Delayed/duplicate/out-of-order delivery may matter")
        if match(text,(r"\bHttpClient\b",r"\baxios\b",r"\bfetch\s*\(",r"\brequests\.",r"\bWebClient\b")):
            t=dep(cs,"external","http","External HTTP dependencies",ev(rp,"outbound HTTP signal","INFERRED"));add_edge(es,own,t,"http","HTTP(S)",ev(rp,"outbound HTTP signal","INFERRED"));unique(c["failureModes"],"Downstream latency/timeouts may propagate")
        if match(text,(r"Authentication",r"Authorization",r"\bJWT\b",r"\bOAuth\b",r"\bOIDC\b")):unique(c["security"],"Authentication/authorization signal present");c["evidence"].append(ev(rp,"security signal"))
        if match(text,(r"OpenTelemetry",r"Serilog",r"ApplicationInsights",r"Prometheus",r"ActivitySource")):unique(c["telemetry"],"Logging/metrics/tracing signal present");c["evidence"].append(ev(rp,"observability signal"))
        if "test" in p.name.lower() or "/test" in rp.lower():unique(c["tests"],rp)
        if p.name=="Dockerfile":unique(c["deployment"],f"Container build: {rp}")

def normalize(items:list[dict[str,Any]],fields:tuple[str,...])->None:
    for x in items:
        for f in fields:x.setdefault(f,[])
        x.setdefault("changeState","unchanged")

def merge(base:list[dict[str,Any]],extra:list[dict[str,Any]])->list[dict[str,Any]]:
    out={str(x["id"]):dict(x) for x in base if x.get("id")}
    for x in extra:
        if not isinstance(x,dict) or not x.get("id"):raise ValueError("explicit model list entries need id")
        k=str(x["id"]);cur=dict(out.get(k,{}))
        for f,v in x.items():
            if isinstance(v,list) and isinstance(cur.get(f),list):
                for e in v:unique(cur[f],e)
            else:cur[f]=v
        out[k]=cur
    return list(out.values())

def baseline(cur:dict[str,Any],old:dict[str,Any]|None)->dict[str,Any]:
    z={"baselineAvailable":False,"addedComponents":[],"removedComponents":[],"changedComponents":[],"addedEdges":[],"removedEdges":[],"baselineFingerprint":None}
    if not old:return z
    oc={x["id"]:x for x in old.get("components",[]) if x.get("id")};nc={x["id"]:x for x in cur["components"]}
    oe={x["id"]:x for x in old.get("edges",[]) if x.get("id")};ne={x["id"]:x for x in cur["edges"]}
    clean=lambda x:{k:v for k,v in x.items() if k not in {"changeState","changedFiles"}}
    return {"baselineAvailable":True,"addedComponents":sorted(nc.keys()-oc.keys()),"removedComponents":sorted(oc.keys()-nc.keys()),"changedComponents":sorted(k for k in oc.keys()&nc.keys() if sha(clean(oc[k]))!=sha(clean(nc[k]))),"addedEdges":sorted(ne.keys()-oe.keys()),"removedEdges":sorted(oe.keys()-ne.keys()),"baselineFingerprint":old.get("evidence",{}).get("modelFingerprint")}

def build(repo:Path,model_path:Path|None=None,changed:list[str]|None=None,old:dict[str,Any]|None=None)->dict[str,Any]:
    repo=repo.expanduser().resolve()
    if not repo.is_dir():raise FileNotFoundError(repo)
    fs=files(repo);cs=roots(repo,fs);es={};compose(repo,fs,cs,es);scan(repo,fs,cs,es)
    explicit={}
    if model_path:
        explicit=json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(explicit,dict):raise ValueError("system model JSON must be an object")
    components=merge(list(cs.values()),list(explicit.get("components") or []));edges=merge(list(es.values()),list(explicit.get("edges") or []))
    normalize(components,("responsibilities","interfaces","state","scaling","failureModes","telemetry","security","deployment","tests","evidence","changedFiles"));normalize(edges,("evidence",))
    for c in components:
        root=str(c.get("path") or ".").rstrip("/")
        hits=[Path(x).as_posix().lstrip("./") for x in changed or [] if root not in {"",".","(logical)","(compose)"} and (Path(x).as_posix().lstrip("./")==root or Path(x).as_posix().lstrip("./").startswith(root+"/"))]
        if hits:c["changeState"]="changed";c["changedFiles"]=sorted(set(hits))
    touched={c["id"] for c in components if c["changeState"]=="changed"}
    for e in edges:
        e.setdefault("kind","dependency");e.setdefault("protocol","UNKNOWN");e.setdefault("asynchronous",False);e.setdefault("timeout","UNKNOWN");e.setdefault("retry","UNKNOWN")
        if e.get("from") in touched or e.get("to") in touched:e["changeState"]="touched"
    inferred_s=[{"id":"deps-"+c["id"],"name":c["name"]+" dependency path","components":[c["id"]]+[e["to"] for e in edges if e.get("from")==c["id"]],"edges":[e["id"] for e in edges if e.get("from")==c["id"]],"steps":["Topology-derived dependency view."],"evidenceLabel":"INFERRED"} for c in components if c["kind"] in {"frontend","service","application"} and any(e.get("from")==c["id"] for e in edges)]
    scenarios=merge(inferred_s,list(explicit.get("scenarios") or []))
    inferred_f=[{"id":"failure-"+c["id"],"name":c["name"]+" unavailable or slow","startComponent":c["id"],"notes":["Graph reachability is a hypothesis; runtime behavior depends on resilience and state."],"evidenceLabel":"INFERRED"} for c in components if c["kind"] in {"service","database","cache","messaging","external"}]
    failures=merge(inferred_f,list(explicit.get("failures") or []))
    parts=[]
    for p in sorted(fs,key=lambda x:rel(repo,x)):
        try:parts.append(rel(repo,p)+hashlib.sha256(p.read_bytes()[:750_000]).hexdigest())
        except OSError:pass
    source=hashlib.sha256("".join(parts).encode()).hexdigest()
    out={"generatedAt":datetime.now(timezone.utc).isoformat(),"repository":{"path":str(repo),"name":repo.name,"commit":git(repo,"rev-parse","HEAD"),"branch":git(repo,"branch","--show-current")},"evidence":{"sourceFingerprint":source,"labels":["CONFIRMED BY CODE","CONFIRMED BY RUNTIME","DOCUMENTED INTENT","INFERRED","UNKNOWN","LEARNER ASSUMPTION"]},"components":sorted(components,key=lambda x:(x["kind"],x["name"])),"edges":sorted(edges,key=lambda x:x["id"]),"scenarios":scenarios,"failures":failures,"decisions":list(explicit.get("decisions") or []),"changedFiles":sorted(set(changed or []))}
    out["evidence"]["modelFingerprint"]=sha({k:v for k,v in out.items() if k!="generatedAt"});out["changes"]=baseline(out,old);return out

def render(m:dict[str,Any])->str:
    data=json.dumps(m,ensure_ascii=False).replace("</","<\\/")
    title=html.escape(m["repository"]["name"])
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Forge System Lab — {title}</title>
<style>:root{{color-scheme:light dark;font-family:system-ui,sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:Canvas;color:CanvasText}}header{{padding:10px;border-bottom:1px solid #8886;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}h1{{font-size:18px;margin:0}}button,select,input{{font:inherit;padding:5px}}.layout{{display:grid;grid-template-columns:minmax(0,1fr) 390px}}#view{{overflow:auto;min-height:760px;background:color-mix(in srgb,Canvas 94%,CanvasText 6%)}}#stage{{position:relative;width:1500px;height:1000px;transform-origin:0 0}}svg{{position:absolute;inset:0;width:1500px;height:1000px;overflow:visible}}.edge{{stroke:CanvasText;stroke-opacity:.35;stroke-width:2;pointer-events:stroke;cursor:pointer}}.edge.dim{{opacity:.12}}.edge.active{{stroke-width:4;stroke-opacity:1}}.node{{position:absolute;width:245px;border:1px solid #8888;border-radius:9px;background:Canvas;box-shadow:0 2px 8px #0002}}.node h3{{font-size:13px;margin:0;padding:8px;cursor:grab;border-bottom:1px solid #8885}}.node .b{{font-size:11px;padding:8px}}.node.dim{{opacity:.2}}.node.active{{border-width:3px}}.node.changed{{outline:3px dashed CanvasText;outline-offset:2px}}aside{{padding:12px;border-left:1px solid #8886;overflow:auto;max-height:calc(100vh - 55px)}}aside h2{{font-size:16px}}aside h3{{font-size:13px}}.muted{{opacity:.7}}.panel{{border-top:1px solid #8886;margin-top:12px;padding-top:8px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px}}.metric{{border:1px solid #8886;border-radius:6px;padding:6px}}input[type=number]{{width:105px}}input[type=range]{{width:100%}}@media(max-width:1000px){{.layout{{grid-template-columns:1fr}}aside{{border-left:0;border-top:1px solid #8886;max-height:none}}}}</style></head>
<body><header><h1>Project Forge System Lab — {title}</h1><label>Lens <select id="lens"></select></label><label>Scenario <select id="scenario"></select></label><input id="search" placeholder="Search"><button id="minus">−</button><button id="plus">+</button><button id="reset">Reset</button><span id="status" class="muted"></span></header><div class="layout"><div id="view"><div id="stage"><svg id="edges"></svg><div id="nodes"></div></div></div><aside id="details"></aside></div>
<script>
const D={data},L=['architecture','runtime','api','data','failure','capacity','performance','observability','security','messaging','deployment','testing','changes','evolution','interview'],C=new Map(D.components.map(x=>[x.id,x])),E=new Map(D.edges.map(x=>[x.id,x])),P=new Map();let S=null,sel=null,fail=null,reveal=false,z=1;
const lens=document.querySelector('#lens'),scenario=document.querySelector('#scenario'),search=document.querySelector('#search');lens.innerHTML=L.map(x=>`<option>${{x}}</option>`).join('');scenario.innerHTML='<option value="">All system</option>'+D.scenarios.map((x,i)=>`<option value="${{i}}">${{h(x.name)}}</option>`).join('');D.components.forEach((x,i)=>P.set(x.id,{{x:30+(i%4)*350,y:30+Math.floor(i/4)*245}}));
function h(v){{return String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c])}}function list(t,x){{return x?.length?`<h3>${{h(t)}}</h3><ul>${{x.map(v=>`<li>${{h(typeof v==='string'?v:JSON.stringify(v))}}</li>`).join('')}}</ul>`:''}}
function lensIds(){{let v=lens.value;if(v==='api')return new Set(D.components.filter(c=>c.interfaces?.length||c.kind==='frontend').map(c=>c.id));if(v==='data')return new Set(D.components.filter(c=>['database','cache'].includes(c.kind)||c.state?.length).map(c=>c.id));if(v==='observability')return new Set(D.components.filter(c=>c.telemetry?.length).map(c=>c.id));if(v==='security')return new Set(D.components.filter(c=>c.security?.length||['frontend','external'].includes(c.kind)).map(c=>c.id));if(v==='messaging')return new Set(D.components.filter(c=>c.kind==='messaging').map(c=>c.id));if(v==='deployment')return new Set(D.components.filter(c=>c.deployment?.length).map(c=>c.id));if(v==='testing')return new Set(D.components.filter(c=>c.tests?.length).map(c=>c.id));if(v==='changes')return new Set([...D.components.filter(c=>c.changeState==='changed').map(c=>c.id),...(D.changes?.addedComponents||[]),...(D.changes?.changedComponents||[])]);return new Set(D.components.map(c=>c.id))}}
function render(){{let n=document.querySelector('#nodes'),ids=lensIds(),sn=new Set(S?.components||[]),q=search.value.toLowerCase();n.innerHTML='';D.components.forEach(c=>{{if(q&&!`${{c.name}} ${{c.kind}} ${{c.path}}`.toLowerCase().includes(q))return;let p=P.get(c.id),e=document.createElement('section');e.className='node';e.dataset.id=c.id;e.style.left=p.x+'px';e.style.top=p.y+'px';let ok=ids.has(c.id)&&(!S||sn.has(c.id));if(!ok)e.classList.add('dim');else if(S)e.classList.add('active');if(c.changeState==='changed'||D.changes?.addedComponents?.includes(c.id)||D.changes?.changedComponents?.includes(c.id))e.classList.add('changed');e.innerHTML=`<h3>${{h(c.name)}} <span class="muted">${{h(c.kind)}}</span></h3><div class="b">${{h(c.path)}}<br><span class="muted">${{h(c.responsibilities?.[0]||'Select for evidence')}}</span></div>`;e.onclick=()=>{{sel={{t:'n',id:c.id}};details()}};drag(e,c.id);n.appendChild(e)}});requestAnimationFrame(draw);details();document.querySelector('#status').textContent=`current · ${{D.repository.commit?.slice(0,8)||'no git'}} · ${{D.evidence.modelFingerprint.slice(0,10)}}`}}
function draw(){{let svg=document.querySelector('#edges'),ids=lensIds(),se=new Set(S?.edges||[]),sn=new Set(S?.components||[]);svg.innerHTML='';D.edges.forEach(e=>{{let a=document.querySelector(`[data-id="${{CSS.escape(e.from)}}"]`),b=document.querySelector(`[data-id="${{CSS.escape(e.to)}}"]`);if(!a||!b)return;let x=P.get(e.from),y=P.get(e.to),l=document.createElementNS('http://www.w3.org/2000/svg','line');l.setAttribute('x1',x.x+245);l.setAttribute('y1',x.y+55);l.setAttribute('x2',y.x);l.setAttribute('y2',y.y+55);l.setAttribute('class','edge');let ok=(ids.has(e.from)||ids.has(e.to))&&(!S||se.has(e.id)||(sn.has(e.from)&&sn.has(e.to)));if(!ok)l.classList.add('dim');else if(S||e.changeState==='touched')l.classList.add('active');l.onclick=()=>{{sel={{t:'e',id:e.id}};details()}};svg.appendChild(l)}})}}
function drag(n,id){{let s=null;n.querySelector('h3').onpointerdown=e=>{{e.preventDefault();n.setPointerCapture(e.pointerId);let p=P.get(id);s={{x:e.clientX,y:e.clientY,px:p.x,py:p.y}}}};n.onpointermove=e=>{{if(!s)return;let p={{x:s.px+(e.clientX-s.x)/z,y:s.py+(e.clientY-s.y)/z}};P.set(id,p);n.style.left=p.x+'px';n.style.top=p.y+'px';draw()}};n.onpointerup=()=>s=null}}
function base(){{let c=D.changes||{{}};return `<h2>System evidence</h2><p><b>Commit:</b> ${{h(D.repository.commit||'UNKNOWN')}}</p><p><b>Fingerprint:</b> ${{h(D.evidence.modelFingerprint)}}</p>${{c.baselineAvailable?`<p>Prior snapshot: +${{c.addedComponents.length}} −${{c.removedComponents.length}} ~${{c.changedComponents.length}} components</p>`:'<p class="muted">No prior disposable snapshot.</p>'}}`}}
function details(){{let o=base();if(sel?.t==='n'){{let c=C.get(sel.id);o+=`<div class="panel"><h2>${{h(c.name)}}</h2><p>${{h(c.kind)}} · ${{h(c.path)}}</p>${{list('Responsibilities',c.responsibilities)}}${{list('Interfaces',c.interfaces)}}${{list('State',c.state)}}${{list('Failure modes',c.failureModes)}}${{list('Telemetry',c.telemetry)}}${{list('Security',c.security)}}${{list('Deployment',c.deployment)}}${{list('Tests',c.tests)}}${{list('Evidence',c.evidence?.map(x=>`${{x.label}} — ${{x.path}} — ${{x.reason}}`))}}${{list('Changed files',c.changedFiles)}}${{['database','cache'].includes(c.kind)?'<p><b>Deep dive:</b> <code>/db-lab</code></p>':''}}</div>`}}if(sel?.t==='e'){{let e=E.get(sel.id);o+=`<div class="panel"><h2>Dependency</h2><p>${{h(C.get(e.from)?.name||e.from)}} → ${{h(C.get(e.to)?.name||e.to)}}</p><p>${{h(e.kind)}} · ${{h(e.protocol)}} · async: ${{e.asynchronous?'yes':'no'}}</p><p>timeout: ${{h(e.timeout)}} · retry: ${{h(e.retry)}}</p>${{list('Evidence',e.evidence?.map(x=>`${{x.label}} — ${{x.path}} — ${{x.reason}}`))}}</div>`}}if(S)o+=`<div class="panel"><h2>Scenario — ${{h(S.name)}}</h2><p>Evidence: ${{h(S.evidenceLabel||'UNKNOWN')}}</p>${{list('Steps',S.steps)}}</div>`;o+=special();document.querySelector('#details').innerHTML=o;wire()}}
function special(){{let v=lens.value;if(v==='failure')return failure();if(v==='capacity')return capacity();if(v==='performance')return latency();if(v==='changes')return `<div class="panel"><h2>Architecture changes</h2>${{list('Added components',D.changes.addedComponents)}}${{list('Removed components',D.changes.removedComponents)}}${{list('Changed components',D.changes.changedComponents)}}${{list('Added dependencies',D.changes.addedEdges)}}${{list('Removed dependencies',D.changes.removedEdges)}}${{list('Work-item files',D.changedFiles)}}<p class="muted">Touched does not prove runtime behavior changed.</p></div>`;if(v==='evolution')return `<div class="panel"><h2>Scale/evolution</h2><label>Traffic multiplier <b id="scaleLabel">1x</b><input id="scale" type="range" min="1" max="100" value="1"></label><div id="scaleText"></div></div>`;if(v==='interview')return `<div class="panel"><h2>Interview perturbation</h2><button id="perturb">Change constraint</button><p id="pert"></p><ol><li>requirements</li><li>scale</li><li>API/data</li><li>architecture</li><li>deep dive</li><li>failure/reliability</li><li>security/observability</li><li>evolution/defense</li></ol></div>`;let prompts={{api:['What are compatibility/versioning constraints?','Where do validation, auth and idempotency live?','How are partial failures represented?'],observability:['Which signal distinguishes app from dependency latency?','Where should traces/spans exist?','Which saturation metric predicts user impact?'],security:['Where are trust boundaries?','Where are authn/authz enforced?','Where can PII/secrets cross boundaries?','What abuse/rate limits are justified?'],messaging:['What can happen twice?','What can arrive out of order?','Where does idempotency live?','What happens after retries exhaust?'],testing:['Which boundaries have integration/contract coverage?','Which failure paths are exercised?','Where would unit tests give false confidence?'],deployment:['How is health/readiness proven?','How do rollout and rollback work?','What is the failure domain?']}};return `<div class="panel"><h2>Design defense</h2><ul>${{(prompts[v]||['Why this boundary?','What simpler alternative exists?','What fails first at 10x?','What evidence justifies more complexity?']).map(x=>`<li>${{h(x)}}</li>`).join('')}}</ul></div>`}}
function failure(){{return `<div class="panel"><h2>Failure exploration</h2><select id="failure"><option value="">Choose failure</option>${{D.failures.map((x,i)=>`<option value="${{i}}" ${{fail===i?'selected':''}}>${{h(x.name)}}</option>`).join('')}}</select><p><b>Predict first:</b> callers, state, queues, retries and user-visible outcome?</p><button id="reveal" ${{fail===null?'disabled':''}}>${{reveal?'Hide':'Reveal likely propagation'}}</button><div>${{reveal?blast():''}}</div></div>`}}
function blast(){{let f=D.failures[fail],rev=new Map();D.edges.forEach(e=>{{if(!rev.has(e.to))rev.set(e.to,[]);rev.get(e.to).push(e.from)}});let seen=new Set([f.startComponent]),q=[f.startComponent];while(q.length)(rev.get(q.shift())||[]).forEach(x=>{{if(!seen.has(x)){{seen.add(x);q.push(x)}}}});return `<p><b>Topological hypothesis, not runtime proof.</b></p><p>${{[...seen].map(x=>h(C.get(x)?.name||x)).join(' → ')}}</p>${{list('Known notes',f.notes)}}`}}
function capacity(){{return `<div class="panel"><h2>Capacity playground</h2><p class="muted">LEARNER ASSUMPTIONS</p><div class="grid">${{[['dau','DAU',5000000],['rpd','Req/user/day',20],['peak','Peak multiplier',8],['write','Write %',10],['payload','Payload KB',4],['days','Retention days',365]].map(x=>`<label>${{x[1]}}<br><input id="${{x[0]}}" type="number" value="${{x[2]}}"></label>`).join('')}}</div><div id="cap"></div></div>`}}
function calcCap(){{let dau=+q('#dau').value,rpd=+q('#rpd').value,p=+q('#peak').value,w=+q('#write').value/100,kb=+q('#payload').value,d=+q('#days').value,avg=dau*rpd/86400,pk=avg*p,wr=pk*w,bw=pk*kb/1024,daily=dau*rpd*w*kb/1048576;q('#cap').innerHTML=`<div class="grid panel"><div class="metric">Avg RPS<br><b>${{avg.toFixed(1)}}</b></div><div class="metric">Peak RPS<br><b>${{pk.toFixed(1)}}</b></div><div class="metric">Peak writes/s<br><b>${{wr.toFixed(1)}}</b></div><div class="metric">Bandwidth<br><b>${{bw.toFixed(1)}} MB/s</b></div><div class="metric">Write data/day<br><b>${{daily.toFixed(1)}} MB</b></div><div class="metric">Retained<br><b>${{(daily*d/1024).toFixed(1)}} GB</b></div></div><p class="muted">Teaching approximation; excludes replication, indexes, compression, protocol overhead and read amplification.</p>`}}
function latency(){{return `<div class="panel"><h2>Latency budget</h2><div class="grid">${{[['target','Target',300],['network','Network',40],['gateway','Gateway',10],['app','Application',25],['db','Datastore',80],['ext','External',100]].map((x,i)=>`<label>${{x[1]}} ms<br><input id="${{x[0]}}" class="${{i?'lat':''}}" type="number" value="${{x[2]}}"></label>`).join('')}}</div><div id="latout"></div></div>`}}
function calcLat(){{let t=+q('#target').value,total=[...document.querySelectorAll('.lat')].reduce((s,x)=>s+(+x.value||0),0);q('#latout').innerHTML=`<p><b>${{total}} ms</b> vs target <b>${{t}} ms</b> — ${{total<=t?'within':'over'}} budget</p><p class="muted">Sequential-sum teaching model; measured tail latency/fan-out can differ.</p>`}}
function q(s){{return document.querySelector(s)}}function wire(){{q('#failure')?.addEventListener('change',e=>{{fail=e.target.value===''?null:+e.target.value;reveal=false;details()}});q('#reveal')?.addEventListener('click',()=>{{reveal=!reveal;details()}});['#dau','#rpd','#peak','#write','#payload','#days'].forEach(x=>q(x)?.addEventListener('input',calcCap));if(q('#dau'))calcCap();q('#target')?.addEventListener('input',calcLat);document.querySelectorAll('.lat').forEach(x=>x.addEventListener('input',calcLat));if(q('#target'))calcLat();q('#scale')?.addEventListener('input',e=>{{q('#scaleLabel').textContent=e.target.value+'x';q('#scaleText').innerHTML='<ul><li>Which current component saturates first?</li><li>What measurement proves it?</li><li>Can the current design scale before adding a subsystem?</li><li>What new failure modes would change introduce?</li></ul>'}});if(q('#scale'))q('#scale').dispatchEvent(new Event('input'));q('#perturb')?.addEventListener('click',()=>{{let a=['Traffic is 20x higher.','An external dependency is unreliable.','Multi-region is now required.','Data cannot leave one legal region.','p99 must stay below 200 ms.','Schema changes must be zero-downtime.','Messages may be duplicated.','Cost must drop materially.','A public endpoint is being abused.'];q('#pert').textContent=a[Math.floor(Math.random()*a.length)]}})}}
lens.onchange=()=>{{sel=null;render()}};scenario.onchange=()=>{{S=scenario.value===''?null:D.scenarios[+scenario.value];render()}};search.oninput=render;q('#plus').onclick=()=>{{z=Math.min(1.8,z+.1);q('#stage').style.transform=`scale(${{z}})`}};q('#minus').onclick=()=>{{z=Math.max(.5,z-.1);q('#stage').style.transform=`scale(${{z}})`}};q('#reset').onclick=()=>{{z=1;q('#stage').style.transform='scale(1)';q('#view').scrollTo(0,0)}};render();
</script></body></html>'''

def export(repo:Path,out:Path,model:Path|None=None,changed:list[str]|None=None,use_baseline:bool=True)->tuple[Path,Path]:
    out=out.expanduser().resolve();old=None;jp=out/"workbench.json"
    if use_baseline and jp.is_file():
        try:old=json.loads(jp.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):pass
    m=build(repo,model,changed,old);out.mkdir(parents=True,exist_ok=True);jp.write_text(json.dumps(m,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");hp=out/"index.html";hp.write_text(render(m),encoding="utf-8");return hp,jp

def main()->int:
    p=argparse.ArgumentParser(description="Generate a read-only interactive system-design learning workbench.");s=p.add_subparsers(dest="cmd",required=True);x=s.add_parser("export");x.add_argument("--repo",required=True,type=Path);x.add_argument("--out",required=True,type=Path);x.add_argument("--model",type=Path);x.add_argument("--changed-file",action="append",default=[]);x.add_argument("--no-baseline",action="store_true");a=p.parse_args()
    if a.cmd=="export":
        hp,jp=export(a.repo,a.out,a.model,a.changed_file,not a.no_baseline);print(f"Generated current view: {hp}");print(f"Evidence:               {jp}");return 0
    return 2

if __name__=="__main__":raise SystemExit(main())
