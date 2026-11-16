#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

IGNORE_DIRS = {".git", ".project-forge", "node_modules", "bin", "obj", "dist", "build", "target", ".venv", "venv", "__pycache__"}
DEFAULT_CACHE = Path(".project-forge/docs-cache")
DEFAULT_SITE = Path(".project-forge/docs-site")
MANIFEST = Path("docs/project-forge-docs.json")
SITE_MARKER = ".project-forge-docs-site"
SITE_MARKER_CONTENT = "project-forge-docs-site\n"


class DocsSiteError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise DocsSiteError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DocsSiteError(f"Expected an object in {path}")
    return value


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value else None


def _safe_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise DocsSiteError(f"Documentation path escapes repository root: {path}") from exc


def _markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"[`*_]", "", match.group(1)).strip()
    return fallback


def _manifest_documents(root: Path, manifest: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    docs: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    if manifest is not None:
        if manifest.get("schemaVersion") != 1:
            warnings.append("docs/project-forge-docs.json schemaVersion is not 1")
        raw = manifest.get("documents")
        if raw is not None and not isinstance(raw, list):
            warnings.append("docs/project-forge-docs.json documents must be an array")
            raw = []
        for index, item in enumerate(raw or []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                warnings.append(f"docs/project-forge-docs.json documents[{index}] is invalid")
                continue
            raw_path = item["path"]
            windows_path = PureWindowsPath(raw_path)
            relative_path = PurePosixPath(raw_path.replace("\\", "/"))
            if (
                relative_path.is_absolute()
                or windows_path.root
                or windows_path.drive
                or ".." in relative_path.parts
            ):
                warnings.append(f"Skipped unsafe documentation path: {item['path']}")
                continue
            rel = relative_path.as_posix()
            path = root / rel
            try:
                resolved_path = root / _safe_rel(root, path)
            except DocsSiteError:
                warnings.append(f"Skipped unsafe documentation path: {item['path']}")
                continue
            seen.add(rel)
            if not resolved_path.is_file():
                if item.get("optional") is not True:
                    warnings.append(f"Listed documentation is not present: {rel}")
                continue
            content = resolved_path.read_text(encoding="utf-8", errors="replace")
            docs.append(
                {
                    "path": rel,
                    "title": str(item.get("title") or _markdown_title(content, path.stem)),
                    "section": str(item.get("section") or "Other"),
                    "type": str(item.get("type") or "markdown"),
                    "ownership": str(item.get("ownership") or "project"),
                    "authority": str(item.get("authority") or "reference"),
                    "content": content,
                }
            )

    candidates: list[Path] = []
    for name in ("PROJECT_BRIEF.md", "README.md"):
        path = root / name
        if path.is_file():
            candidates.append(path)
    docs_root = root / "docs"
    if docs_root.is_dir():
        if _path_contains_link(docs_root):
            warnings.append(f"Skipped unsafe documentation directory: {docs_root}")
        else:
            for base, dirs, names in os.walk(docs_root):
                safe_dirs = []
                for directory in dirs:
                    candidate = Path(base) / directory
                    if directory in IGNORE_DIRS:
                        continue
                    if _is_link(candidate):
                        warnings.append(f"Skipped unsafe documentation directory: {candidate}")
                        continue
                    safe_dirs.append(directory)
                dirs[:] = safe_dirs
                for name in names:
                    if name.lower().endswith(".md"):
                        candidates.append(Path(base) / name)

    for path in sorted(candidates):
        try:
            rel = _safe_rel(root, path)
        except DocsSiteError:
            warnings.append(f"Skipped unsafe documentation path: {path}")
            continue
        if rel in seen:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        section = "Overview" if rel in {"README.md", "PROJECT_BRIEF.md", "docs/index.md"} else rel.split("/")[1].replace("-", " ").title() if rel.startswith("docs/") and "/" in rel else "Other"
        docs.append(
            {
                "path": rel,
                "title": _markdown_title(content, path.stem),
                "section": section,
                "type": "markdown",
                "ownership": "unknown",
                "authority": "reference",
                "content": content,
            }
        )

    docs.sort(key=lambda item: (item["section"].lower(), item["path"].lower()))
    return docs, warnings


def _lab_status(root: Path, kind: str, current_commit: str | None) -> dict[str, Any]:
    cache = root / DEFAULT_CACHE / kind
    data_path = cache / "workbench.json"
    index_path = cache / "index.html"
    command = (
        "python tools/project-forge-system-lab/system-workbench.py export --repo . --out .project-forge/docs-cache/system"
        if kind == "system"
        else "/db-lab"
    )
    result: dict[str, Any] = {
        "kind": kind,
        "status": "NOT GENERATED",
        "detail": "No disposable local projection is available.",
        "command": command,
        "hasIndex": index_path.is_file(),
    }
    if not data_path.is_file():
        return result
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["status"] = "AVAILABLE / FRESHNESS UNKNOWN"
        result["detail"] = "A local projection exists, but its evidence metadata could not be read."
        return result

    generated = data.get("generatedAt") if isinstance(data, dict) else None
    if generated:
        result["generatedAt"] = str(generated)

    recorded_commit: str | None = None
    if isinstance(data, dict):
        repository = data.get("repository")
        if isinstance(repository, dict) and repository.get("commit"):
            recorded_commit = str(repository["commit"])
        elif data.get("repositoryCommit"):
            recorded_commit = str(data["repositoryCommit"])

    if recorded_commit and current_commit:
        result["recordedCommit"] = recorded_commit
        if recorded_commit == current_commit:
            result["status"] = "CURRENT"
            result["detail"] = f"Projection evidence is bound to current commit {current_commit[:10]}."
        else:
            result["status"] = "STALE"
            result["detail"] = f"Projection records {recorded_commit[:10]}; checkout is {current_commit[:10]}."
    else:
        result["status"] = "AVAILABLE / FRESHNESS UNKNOWN"
        result["detail"] = "A projection exists, but there is not enough evidence to prove it matches the current checkout."
    return result


def _prepare_system_lab(root: Path) -> str | None:
    tool = root / "tools/project-forge-system-lab/system-workbench.py"
    if not tool.is_file():
        return None
    out = root / DEFAULT_CACHE / "system"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, str(tool), "export", "--repo", str(root), "--out", str(out)],
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"System Lab preparation unavailable: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return "System Lab preparation failed: " + (detail[-1] if detail else f"exit {result.returncode}")
    return None


def _validate_lab_cache(root: Path, kind: str) -> Path:
    source = root / DEFAULT_CACHE / kind
    if _path_contains_link(source):
        raise DocsSiteError(f"Lab cache contains a symlink or junction: {source}")
    if source.exists():
        try:
            source.resolve().relative_to(root)
        except ValueError as exc:
            raise DocsSiteError(f"Lab cache escapes repository root: {source}") from exc
    if source.is_dir() and _directory_contains_link(source):
        raise DocsSiteError(f"Lab cache contains a symlink or junction: {source}")
    return source


def _copy_lab_cache(root: Path, out: Path, kind: str) -> None:
    source = _validate_lab_cache(root, kind)
    target = out / "labs" / kind
    try:
        target.resolve().relative_to(out)
    except ValueError as exc:
        raise DocsSiteError(f"Lab output escapes generated site directory: {target}") from exc
    if _path_contains_link(target):
        raise DocsSiteError(f"Lab output contains a symlink or junction: {target}")
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise DocsSiteError(f"Unexpected lab output path: {target}")
        shutil.rmtree(target)
    if source.is_dir():
        shutil.copytree(source, target)


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _path_contains_link(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if _is_link(current):
            return True
    return False


def _paths_overlap(left: Path, right: Path) -> bool:
    left = Path(os.path.abspath(left))
    right = Path(os.path.abspath(right))
    return left == right or left in right.parents or right in left.parents


def _directory_contains_link(root: Path) -> bool:
    directories = [root]
    while directories:
        current = directories.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                if _is_link(path):
                    return True
                if entry.is_dir(follow_symlinks=False):
                    directories.append(path)
    return False


def _prepare_output(root: Path, out: Path) -> None:
    if _path_contains_link(out):
        raise DocsSiteError(f"Refusing to use an output path containing a symlink or junction: {out}")
    if out == root or out in root.parents:
        raise DocsSiteError(f"Refusing to use the repository root or one of its parents as output: {out}")
    for kind in ("system", "database"):
        cache = root / DEFAULT_CACHE / kind
        if _paths_overlap(out, cache):
            raise DocsSiteError(f"Output path overlaps a lab cache: {cache}")

    if out.exists():
        if not out.is_dir():
            raise DocsSiteError(f"Output path is not a directory: {out}")
        marker = out / SITE_MARKER
        if any(out.iterdir()):
            if marker.is_symlink() or not marker.is_file():
                raise DocsSiteError(f"Refusing to overwrite an unowned output directory: {out}")
            try:
                marker_content = marker.read_text(encoding="utf-8")
            except OSError as exc:
                raise DocsSiteError(f"Unable to verify output ownership: {marker}") from exc
            if marker_content != SITE_MARKER_CONTENT:
                raise DocsSiteError(f"Refusing to overwrite an unowned output directory: {out}")

        if _directory_contains_link(out):
            raise DocsSiteError(f"Refusing to write through a symlink in output directory: {out}")

        for name in (SITE_MARKER, "index.html", "site.json"):
            path = out / name
            if path.is_file():
                try:
                    link_count = path.stat().st_nlink
                except OSError as exc:
                    raise DocsSiteError(f"Unable to verify output file links: {path}") from exc
                if link_count > 1:
                    raise DocsSiteError(f"Refusing to overwrite hard-linked output file: {path}")

    out.mkdir(parents=True, exist_ok=True)
    (out / SITE_MARKER).write_text(SITE_MARKER_CONTENT, encoding="utf-8")


def _site_payload(root: Path) -> dict[str, Any]:
    manifest = _read_json(root / MANIFEST)
    docs, warnings = _manifest_documents(root, manifest)
    current_commit = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    site = manifest.get("site") if isinstance(manifest, dict) and isinstance(manifest.get("site"), dict) else {}
    title = str(site.get("title") or root.name)
    entry = str(site.get("entry") or ("PROJECT_BRIEF.md" if (root / "PROJECT_BRIEF.md").is_file() else "README.md"))
    return {
        "title": title,
        "entry": entry,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "repository": {"name": root.name, "commit": current_commit, "branch": branch},
        "documents": docs,
        "warnings": warnings,
        "labs": {
            "system": _lab_status(root, "system", current_commit),
            "database": _lab_status(root, "database", current_commit),
        },
    }


def _html_document(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(str(payload["title"]))
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Project Docs</title>
<style>
:root{{color-scheme:light dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--line:#8885;--muted:#777;--panel:color-mix(in srgb,Canvas 96%,CanvasText 4%);--accent:LinkText}}
*{{box-sizing:border-box}} body{{margin:0;background:Canvas;color:CanvasText}} a{{color:LinkText}}
header{{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);background:Canvas}}
header h1{{font-size:17px;margin:0;white-space:nowrap}} #search{{flex:1;max-width:620px;padding:7px 9px;font:inherit}}
.repo{{font-size:12px;color:var(--muted);margin-left:auto}}
.layout{{display:grid;grid-template-columns:300px minmax(0,1fr) 300px;min-height:calc(100vh - 52px)}}
nav{{border-right:1px solid var(--line);padding:12px;overflow:auto}} nav h3{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin:16px 4px 6px;color:var(--muted)}}
nav button{{width:100%;text-align:left;border:0;background:none;color:inherit;padding:7px;border-radius:6px;cursor:pointer}} nav button:hover,nav button.active{{background:var(--panel)}} nav small{{display:block;color:var(--muted);overflow:hidden;text-overflow:ellipsis}}
main{{padding:28px clamp(18px,4vw,64px);min-width:0}} article{{max-width:980px;margin:auto;line-height:1.6}} article h1{{font-size:2rem}} article h2{{margin-top:2.2rem;border-bottom:1px solid var(--line);padding-bottom:.25rem}} article pre{{overflow:auto;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}} article code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}} article :not(pre)>code{{padding:.1em .3em;border-radius:4px;background:var(--panel)}} article table{{border-collapse:collapse;width:100%;display:block;overflow:auto}} article th,article td{{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}} article blockquote{{border-left:4px solid var(--line);margin-left:0;padding-left:14px;color:var(--muted)}}
aside{{border-left:1px solid var(--line);padding:12px;overflow:auto}} .card{{border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:10px;background:var(--panel)}} .card h3{{margin:0 0 6px;font-size:14px}} .status{{font-weight:700;font-size:12px}} .muted{{color:var(--muted)}} .badge{{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 6px;font-size:11px;margin-right:4px}} .warning{{border-left:4px solid #b8860b;padding:8px 10px;background:var(--panel);margin:10px 0}}
button.copy{{font:inherit;font-size:12px;padding:4px 7px}} .mermaid-lite{{overflow:auto;border:1px solid var(--line);border-radius:8px;padding:8px;background:var(--panel)}} .mermaid-lite svg{{min-width:680px;width:100%;height:auto}} .mermaid-fallback{{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:12px}}
@media(max-width:1100px){{.layout{{grid-template-columns:250px 1fr}}aside{{display:none}}}} @media(max-width:760px){{.layout{{display:block}}nav{{border-right:0;border-bottom:1px solid var(--line);max-height:280px}}header{{flex-wrap:wrap}}.repo{{width:100%;margin-left:0}}}}
</style>
</head>
<body>
<header><h1 id="siteTitle"></h1><input id="search" type="search" placeholder="Search project docs"><div class="repo" id="repo"></div></header>
<div class="layout"><nav id="nav"></nav><main><article id="doc"></article></main><aside id="side"></aside></div>
<script>
const SITE={data};
const state={{path:SITE.entry,query:''}};
const byPath=new Map(SITE.documents.map(d=>[d.path,d]));
function esc(v){{return String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c])}}
function safeHref(v){{let s=String(v||'').trim();if(!s)return '#';if(/^https?:\/\//i.test(s)||/^mailto:/i.test(s)||/^#/.test(s)||/^[.\w\/-]+(?:#[\w-]+)?$/.test(s))return s;return '#'}}
function inline(v){{let s=esc(v);s=s.replace(/`([^`]+)`/g,'<code>$1</code>');s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');s=s.replace(/\*([^*]+)\*/g,'<em>$1</em>');s=s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,(_,t,u)=>`<a href="${{esc(safeHref(u))}}" target="${{/^https?:/.test(u)?'_blank':'_self'}}">${{t}}</a>`);return s}}
function md(text){{let lines=String(text||'').replace(/\r/g,'').split('\n'),out=[],i=0;while(i<lines.length){{let l=lines[i];if(/^```/.test(l)){{let lang=l.slice(3).trim(),buf=[];i++;while(i<lines.length&&!/^```/.test(lines[i]))buf.push(lines[i++]);i++;let src=buf.join('\n');if(lang==='mermaid')out.push(`<div class="mermaid-lite" data-mermaid="${{esc(src)}}"></div>`);else out.push(`<pre><code>${{esc(src)}}</code></pre>`);continue}}if(/^\|.*\|\s*$/.test(l)&&i+1<lines.length&&/^\|?\s*:?-+/.test(lines[i+1])){{let rows=[];rows.push(l);i+=2;while(i<lines.length&&/^\|.*\|\s*$/.test(lines[i]))rows.push(lines[i++]);let cells=x=>x.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());let h=cells(rows[0]);out.push('<table><thead><tr>'+h.map(c=>`<th>${{inline(c)}}</th>`).join('')+'</tr></thead><tbody>'+rows.slice(1).map(r=>'<tr>'+cells(r).map(c=>`<td>${{inline(c)}}</td>`).join('')+'</tr>').join('')+'</tbody></table>');continue}}let m=l.match(/^(#{{1,6}})\s+(.+)$/);if(m){{let n=m[1].length;out.push(`<h${{n}}>${{inline(m[2])}}</h${{n}}>`);i++;continue}}if(/^---+\s*$/.test(l)){{out.push('<hr>');i++;continue}}if(/^>\s?/.test(l)){{let b=[];while(i<lines.length&&/^>\s?/.test(lines[i]))b.push(lines[i++].replace(/^>\s?/,''));out.push(`<blockquote>${{md(b.join('\n'))}}</blockquote>`);continue}}if(/^[-*+]\s+/.test(l)){{let a=[];while(i<lines.length&&/^[-*+]\s+/.test(lines[i]))a.push(lines[i++].replace(/^[-*+]\s+/,''));out.push('<ul>'+a.map(x=>`<li>${{inline(x)}}</li>`).join('')+'</ul>');continue}}if(/^\d+\.\s+/.test(l)){{let a=[];while(i<lines.length&&/^\d+\.\s+/.test(lines[i]))a.push(lines[i++].replace(/^\d+\.\s+/,''));out.push('<ol>'+a.map(x=>`<li>${{inline(x)}}</li>`).join('')+'</ol>');continue}}if(!l.trim()){{i++;continue}}let p=[l];i++;while(i<lines.length&&lines[i].trim()&&!/^(#|```|>|[-*+]\s+|\d+\.\s+)/.test(lines[i])&&!/^\|.*\|\s*$/.test(lines[i]))p.push(lines[i++]);out.push(`<p>${{inline(p.join(' '))}}</p>`);}}return out.join('\n')}}
function mermaidLite(el){{let src=el.dataset.mermaid||'',first=src.split('\n').find(x=>x.trim())||'';let mm=first.match(/^\s*flowchart\s+(LR|TD)/i);if(!mm){{el.innerHTML=`<div class="mermaid-fallback">${{esc(src)}}</div>`;return}}let dir=mm[1].toUpperCase(),nodes=new Map(),edges=[];for(let raw of src.split('\n').slice(1)){{let l=raw.trim();if(!l||l.startsWith('%%'))continue;let re=/([A-Za-z0-9_-]+)(?:\[([^\]]+)\])?\s*--+>?\s*([A-Za-z0-9_-]+)(?:\[([^\]]+)\])?/;let x=l.match(re);if(x){{nodes.set(x[1],(x[2]||nodes.get(x[1])||x[1]).replace(/<br\s*\/?>/gi,' / '));nodes.set(x[3],(x[4]||nodes.get(x[3])||x[3]).replace(/<br\s*\/?>/gi,' / '));edges.push([x[1],x[3]]);continue}}let n=l.match(/^([A-Za-z0-9_-]+)\[([^\]]+)\]/);if(n)nodes.set(n[1],n[2].replace(/<br\s*\/?>/gi,' / '))}}let ids=[...nodes.keys()];if(!ids.length){{el.innerHTML=`<div class="mermaid-fallback">${{esc(src)}}</div>`;return}}let w=dir==='LR'?Math.max(720,ids.length*190):900,h=dir==='LR'?220:Math.max(260,Math.ceil(ids.length/4)*130),pos=new Map();ids.forEach((id,k)=>{{if(dir==='LR')pos.set(id,{{x:30+k*180,y:70}});else pos.set(id,{{x:30+(k%4)*215,y:35+Math.floor(k/4)*120}})}});let svg=[`<svg viewBox="0 0 ${{w}} ${{h}}" role="img"><defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor"/></marker></defs>`];for(let [a,b] of edges){{let p=pos.get(a),q=pos.get(b);if(!p||!q)continue;svg.push(`<line x1="${{p.x+140}}" y1="${{p.y+35}}" x2="${{q.x}}" y2="${{q.y+35}}" stroke="currentColor" stroke-opacity=".55" marker-end="url(#arr)"/>`)}}for(let id of ids){{let p=pos.get(id),label=nodes.get(id);svg.push(`<rect x="${{p.x}}" y="${{p.y}}" width="140" height="70" rx="9" fill="Canvas" stroke="currentColor" stroke-opacity=".55"/><foreignObject x="${{p.x+8}}" y="${{p.y+8}}" width="124" height="54"><div xmlns="http://www.w3.org/1999/xhtml" style="font:12px system-ui;text-align:center;display:flex;align-items:center;justify-content:center;height:54px">${{esc(label)}}</div></foreignObject>`)}}svg.push('</svg>');el.innerHTML=svg.join('')}}
function nav(){{let q=state.query.toLowerCase(),groups=new Map();for(let d of SITE.documents){{if(q&&!`${{d.title}} ${{d.path}} ${{d.content}}`.toLowerCase().includes(q))continue;let a=groups.get(d.section)||[];a.push(d);groups.set(d.section,a)}}let n=document.querySelector('#nav');n.innerHTML='';for(let [g,ds] of groups){{let h=document.createElement('h3');h.textContent=g;n.appendChild(h);for(let d of ds){{let b=document.createElement('button');b.className=d.path===state.path?'active':'';b.innerHTML=`${{esc(d.title)}}<small>${{esc(d.path)}}</small>`;b.onclick=()=>{{state.path=d.path;render()}};n.appendChild(b)}}}}}}
function labCard(label,l){{let link=l.hasIndex?`<p><a href="labs/${{l.kind}}/index.html" target="_blank">Open existing projection</a></p>`:'';return `<div class="card"><h3>${{esc(label)}}</h3><div class="status">${{esc(l.status)}}</div><p class="muted">${{esc(l.detail)}}</p>${{link}}<p><code>${{esc(l.command)}}</code></p><button class="copy" data-copy="${{esc(l.command)}}">Copy command</button></div>`}}
function side(d){{let s=`<div class="card"><h3>Document</h3><span class="badge">${{esc(d.ownership)}}</span><span class="badge">${{esc(d.authority)}}</span><p class="muted">${{esc(d.path)}}</p></div>`;s+=labCard('System Lab',SITE.labs.system)+labCard('Database Lab',SITE.labs.database);if(SITE.warnings.length)s+=`<div class="card"><h3>Documentation checks</h3>${{SITE.warnings.map(x=>`<div class="warning">${{esc(x)}}</div>`).join('')}}</div>`;s+=`<div class="card"><h3>Learning</h3><p><code>/system-lab</code><br><code>/db-lab</code><br><code>/code-walkthrough</code><br><code>/learning-review</code><br><code>/coach</code></p></div>`;document.querySelector('#side').innerHTML=s;document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>navigator.clipboard?.writeText(b.dataset.copy))}}
function render(){{let d=byPath.get(state.path)||SITE.documents[0];if(!d){{document.querySelector('#doc').innerHTML='<h1>No Markdown documents found</h1>';return}}state.path=d.path;document.querySelector('#doc').innerHTML=md(d.content);document.querySelectorAll('.mermaid-lite').forEach(mermaidLite);nav();side(d);history.replaceState(null,'','#'+encodeURIComponent(d.path))}}
document.querySelector('#siteTitle').textContent=SITE.title;document.querySelector('#repo').textContent=`${{SITE.repository.branch||''}} ${{SITE.repository.commit?SITE.repository.commit.slice(0,10):'no git'}}`;document.querySelector('#search').oninput=e=>{{state.query=e.target.value;nav()}};let h=decodeURIComponent(location.hash.slice(1));if(byPath.has(h))state.path=h;render();
</script>
</body></html>'''


def build(root: Path, out: Path, *, prepare_system_lab: bool = False) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    out = Path(os.path.abspath(out))
    if not root.is_dir():
        raise DocsSiteError(f"Repository root does not exist: {root}")
    for kind in ("system", "database"):
        _validate_lab_cache(root, kind)
    _prepare_output(root, out)
    prep_warning = _prepare_system_lab(root) if prepare_system_lab else None
    payload = _site_payload(root)
    if prep_warning:
        payload["warnings"].append(prep_warning)
    _copy_lab_cache(root, out, "system")
    _copy_lab_cache(root, out, "database")
    index = out / "index.html"
    index.write_text(_html_document(payload), encoding="utf-8")
    (out / "site.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index, payload


def serve(root: Path, out: Path, port: int, *, open_browser: bool, prepare_system_lab: bool) -> int:
    index, payload = build(root, out, prepare_system_lab=prepare_system_lab)
    handler = partial(SimpleHTTPRequestHandler, directory=str(index.parent))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{actual_port}/"
    print(f"Project Forge Project Docs: {url}")
    print(f"Documents: {len(payload['documents'])}")
    print(f"System Lab: {payload['labs']['system']['status']}")
    print(f"Database Lab: {payload['labs']['database']['status']}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or serve the dependency-free Project Forge project documentation site.")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build")
    build_parser.add_argument("--root", type=Path, default=Path("."))
    build_parser.add_argument("--out", type=Path)
    build_parser.add_argument("--prepare-system-lab", action="store_true")

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--root", type=Path, default=Path("."))
    serve_parser.add_argument("--out", type=Path)
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true", dest="open_browser")
    serve_parser.add_argument("--no-system-lab", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    out = args.out if args.out else root / DEFAULT_SITE
    try:
        if args.command == "build":
            index, payload = build(root, out, prepare_system_lab=args.prepare_system_lab)
            print(f"Project Forge Project Docs built: {index}")
            print(f"Documents: {len(payload['documents'])}")
            return 0
        return serve(
            root,
            out,
            args.port,
            open_browser=args.open_browser,
            prepare_system_lab=not args.no_system_lab,
        )
    except DocsSiteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
