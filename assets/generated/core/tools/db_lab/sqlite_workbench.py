#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote


PLAN_INDEX_RE = re.compile(r"\bUSING(?:\s+COVERING)?\s+INDEX\s+([^\s()]+)", re.IGNORECASE)
PLAN_TABLE_RE = re.compile(r"\b(?:SCAN|SEARCH)\s+([^\s()]+)", re.IGNORECASE)
TABLE_REF_RE = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([\[\]`\"A-Za-z0-9_.]+)(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
QUALIFIED_COLUMN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
SQL_KEYWORDS = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "cross",
    "on",
    "order",
    "group",
    "having",
    "limit",
    "offset",
    "union",
    "intersect",
    "except",
    "returning",
    "set",
}


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _clean_identifier(value: str) -> str:
    value = value.strip().strip("[]`\"")
    return value.split(".")[-1]


def _open_read_only(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {resolved}")
    uri_path = quote(resolved.as_posix(), safe="/:")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_xinfo({_literal(name)})").fetchall()
    return [
        {
            "cid": row["cid"],
            "name": row["name"],
            "type": row["type"] or "",
            "notNull": bool(row["notnull"]),
            "default": row["dflt_value"],
            "primaryKeyOrder": row["pk"],
            "hidden": row["hidden"],
        }
        for row in rows
    ]


def _foreign_keys(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA foreign_key_list({_literal(name)})").fetchall()
    return [
        {
            "id": row["id"],
            "sequence": row["seq"],
            "toTable": row["table"],
            "fromColumn": row["from"],
            "toColumn": row["to"],
            "onUpdate": row["on_update"],
            "onDelete": row["on_delete"],
            "match": row["match"],
        }
        for row in rows
    ]


def _indexes(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in conn.execute(f"PRAGMA index_list({_literal(table)})").fetchall():
        name = row["name"]
        columns: list[dict[str, Any]] = []
        for item in conn.execute(f"PRAGMA index_xinfo({_literal(name)})").fetchall():
            if item["key"] == 0:
                continue
            columns.append(
                {
                    "sequence": item["seqno"],
                    "cid": item["cid"],
                    "name": item["name"],
                    "descending": bool(item["desc"]),
                    "collation": item["coll"],
                }
            )
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_schema WHERE type='index' AND name=?", (name,)
        ).fetchone()
        result.append(
            {
                "name": name,
                "unique": bool(row["unique"]),
                "origin": row["origin"],
                "partial": bool(row["partial"]),
                "columns": columns,
                "sql": sql_row["sql"] if sql_row else None,
            }
        )
    return result


def inspect_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    objects = conn.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()

    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for obj in objects:
        name = obj["name"]
        is_table = obj["type"] == "table"
        columns = _columns(conn, name)
        fks = _foreign_keys(conn, name) if is_table else []
        indexes = _indexes(conn, name) if is_table else []
        fk_columns = {fk["fromColumn"] for fk in fks}
        payload_columns = [
            col for col in columns if col["name"] not in fk_columns and not col["primaryKeyOrder"]
        ]
        junction_candidate = len(fks) >= 2 and len(payload_columns) <= 2
        entity = {
            "name": name,
            "kind": obj["type"],
            "sql": obj["sql"],
            "columns": columns,
            "foreignKeys": fks,
            "indexes": indexes,
            "junctionCandidate": junction_candidate,
        }
        entities.append(entity)
        for fk in fks:
            relationships.append(
                {
                    "fromTable": name,
                    "fromColumn": fk["fromColumn"],
                    "toTable": fk["toTable"],
                    "toColumn": fk["toColumn"],
                    "onUpdate": fk["onUpdate"],
                    "onDelete": fk["onDelete"],
                }
            )

    return {"entities": entities, "relationships": relationships}


def _normalize_parameters(parameters: Any) -> Any:
    if isinstance(parameters, dict):
        return {str(key).lstrip(":@$?"): value for key, value in parameters.items()}
    if isinstance(parameters, list):
        return parameters
    if parameters is None:
        return {}
    raise ValueError("query parameters must be an object, array, or null")


def _aliases_and_tables(sql: str, known_tables: set[str]) -> tuple[dict[str, str], list[str]]:
    aliases: dict[str, str] = {}
    tables: list[str] = []
    for match in TABLE_REF_RE.finditer(sql):
        table = _clean_identifier(match.group(1))
        alias = match.group(2)
        if table not in known_tables:
            continue
        if table not in tables:
            tables.append(table)
        aliases[table] = table
        if alias and alias.lower() not in SQL_KEYWORDS:
            aliases[alias] = table
    return aliases, tables


def _referenced_columns(sql: str, aliases: dict[str, str], known_tables: set[str]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for qualifier, column in QUALIFIED_COLUMN_RE.findall(sql):
        table = aliases.get(qualifier)
        if not table and qualifier in known_tables:
            table = qualifier
        if not table:
            continue
        key = (table, column)
        if key in seen:
            continue
        seen.add(key)
        result.append({"table": table, "column": column})
    return result


def _plan_for_query(conn: sqlite3.Connection, sql: str, parameters: Any) -> tuple[list[dict[str, Any]], str | None]:
    first_keyword = re.match(r"\s*(?:--[^\n]*\n\s*)*([A-Za-z]+)", sql)
    if not first_keyword or first_keyword.group(1).upper() not in {"SELECT", "WITH"}:
        return [], "Query plan is only collected for SELECT/WITH statements."
    try:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql, _normalize_parameters(parameters)).fetchall()
    except sqlite3.Error as exc:
        return [], str(exc)
    return [
        {"id": row[0], "parent": row[1], "notUsed": row[2], "detail": row[3]}
        for row in rows
    ], None


def analyze_queries(conn: sqlite3.Connection, query_specs: list[dict[str, Any]], schema: dict[str, Any]) -> list[dict[str, Any]]:
    known_tables = {entity["name"] for entity in schema["entities"]}
    analyzed: list[dict[str, Any]] = []
    for position, spec in enumerate(query_specs, start=1):
        sql = str(spec.get("sql") or "").strip()
        if not sql:
            raise ValueError(f"query #{position} is missing sql")
        name = str(spec.get("name") or f"Query {position}")
        parameters = spec.get("parameters")
        aliases, tables = _aliases_and_tables(sql, known_tables)
        columns = _referenced_columns(sql, aliases, known_tables)
        plan, plan_error = _plan_for_query(conn, sql, parameters)
        used_indexes: list[str] = []
        plan_tables: list[str] = []
        for step in plan:
            detail = step["detail"] or ""
            index_match = PLAN_INDEX_RE.search(detail)
            if index_match:
                index_name = _clean_identifier(index_match.group(1))
                if index_name not in used_indexes:
                    used_indexes.append(index_name)
            table_match = PLAN_TABLE_RE.search(detail)
            if table_match:
                table_name = _clean_identifier(table_match.group(1))
                if table_name in known_tables and table_name not in plan_tables:
                    plan_tables.append(table_name)
        for table in plan_tables:
            if table not in tables:
                tables.append(table)
        analyzed.append(
            {
                "name": name,
                "sql": sql,
                "parameters": parameters,
                "tables": tables,
                "columns": columns,
                "plan": plan,
                "planError": plan_error,
                "usedIndexes": used_indexes,
            }
        )
    return analyzed


def _load_query_specs(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("queries JSON must be an array")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each query entry must be an object")
    return data


def build_model(db_path: Path, queries_path: Path | None = None) -> dict[str, Any]:
    with _open_read_only(db_path) as conn:
        schema = inspect_schema(conn)
        queries = analyze_queries(conn, _load_query_specs(queries_path), schema)
        return {
            "database": {
                "path": str(db_path.expanduser().resolve()),
                "engine": "SQLite",
                "sqliteVersion": sqlite3.sqlite_version,
            },
            **schema,
            "queries": queries,
        }


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_html(model: dict[str, Any]) -> str:
    data = _json_for_script(model)
    title = html.escape(Path(model["database"]["path"]).name)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Project Forge DB Lab — {title}</title>
<style>
:root {{ color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; background: Canvas; color: CanvasText; }}
header {{ padding: 12px 16px; border-bottom: 1px solid color-mix(in srgb, CanvasText 20%, transparent); display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
header h1 {{ margin:0; font-size:18px; }}
.controls {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
select, button {{ font: inherit; padding:6px 8px; }}
.layout {{ display:grid; grid-template-columns:minmax(0,1fr) 360px; min-height:calc(100vh - 58px); }}
#viewport {{ overflow:auto; position:relative; min-height:700px; background: color-mix(in srgb, Canvas 94%, CanvasText 6%); }}
#canvas {{ position:relative; min-width:900px; min-height:700px; }}
#edges {{ position:absolute; inset:0; pointer-events:none; overflow:visible; }}
.edge {{ stroke: color-mix(in srgb, CanvasText 35%, transparent); stroke-width:2; }}
.edge.active {{ stroke: CanvasText; stroke-width:4; }}
.card {{ position:absolute; width:270px; border:1px solid color-mix(in srgb, CanvasText 28%, transparent); border-radius:10px; background:Canvas; box-shadow:0 2px 10px color-mix(in srgb, CanvasText 10%, transparent); overflow:hidden; transition:opacity .15s, transform .15s, border-color .15s; }}
.card.query-hit {{ border-width:3px; transform:translateY(-2px); }}
.card.dim {{ opacity:.28; }}
.card.hidden {{ display:none; }}
.card h3 {{ margin:0; padding:9px 10px; font-size:14px; border-bottom:1px solid color-mix(in srgb, CanvasText 18%, transparent); cursor:pointer; }}
.badge {{ font-size:10px; opacity:.7; margin-left:6px; }}
.columns, .indexes {{ list-style:none; margin:0; padding:0; }}
.columns li, .indexes li {{ padding:5px 9px; border-bottom:1px solid color-mix(in srgb, CanvasText 9%, transparent); font-size:12px; cursor:pointer; }}
.columns li.hit {{ font-weight:700; text-decoration:underline; }}
.indexes li.used {{ font-weight:800; }}
.indexes li.candidate:not(.used) {{ font-style:italic; }}
.section-title {{ padding:6px 9px; font-size:10px; font-weight:700; text-transform:uppercase; opacity:.65; }}
aside {{ border-left:1px solid color-mix(in srgb, CanvasText 20%, transparent); padding:14px; overflow:auto; }}
aside h2 {{ font-size:16px; margin:0 0 10px; }}
aside h3 {{ font-size:13px; margin:16px 0 6px; }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; font-size:11px; padding:9px; border-radius:8px; background:color-mix(in srgb, Canvas 88%, CanvasText 12%); }}
.kv {{ display:grid; grid-template-columns:110px 1fr; gap:4px 8px; font-size:12px; }}
.legend {{ font-size:11px; opacity:.8; }}
.legend span {{ margin-right:10px; }}
@media (max-width: 1000px) {{ .layout {{ grid-template-columns:1fr; }} aside {{ border-left:0; border-top:1px solid color-mix(in srgb, CanvasText 20%, transparent); }} }}
</style>
</head>
<body>
<header>
  <h1>Project Forge DB Lab — {title}</h1>
  <div class=\"controls\">
    <label>Query <select id=\"querySelect\"></select></label>
    <label>View <select id=\"groupSelect\"><option value=\"all\">All tables</option><option value=\"query\">Query tables</option><option value=\"connected\">Related tables</option><option value=\"junction\">Junction candidates</option></select></label>
  </div>
  <div class=\"legend\"><span><b>bold index</b> = planner selected</span><span><i>italic index</i> = candidate/relevant</span></div>
</header>
<div class=\"layout\">
  <div id=\"viewport\"><div id=\"canvas\"><svg id=\"edges\"></svg><div id=\"cards\"></div></div></div>
  <aside id=\"details\"></aside>
</div>
<script>
const DATA = {data};
const entities = new Map(DATA.entities.map(e => [e.name, e]));
let activeQuery = null;
let selected = null;

const qSelect = document.getElementById('querySelect');
qSelect.innerHTML = '<option value="">No query highlighting</option>' + DATA.queries.map((q,i)=>`<option value="${{i}}">${{escapeHtml(q.name)}}</option>`).join('');
qSelect.disabled = DATA.queries.length === 0;
qSelect.addEventListener('change', () => {{ activeQuery = qSelect.value === '' ? null : DATA.queries[Number(qSelect.value)]; render(); }});
document.getElementById('groupSelect').addEventListener('change', render);
window.addEventListener('resize', () => requestAnimationFrame(drawEdges));

function escapeHtml(value) {{ return String(value ?? '').replace(/[&<>\"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}})[c]); }}
function columnKey(table, column) {{ return `${{table}}.${{column}}`; }}
function queryColumnKeys() {{ return new Set((activeQuery?.columns || []).map(c => columnKey(c.table,c.column))); }}
function queryTables() {{ return new Set(activeQuery?.tables || []); }}
function usedIndexes() {{ return new Set(activeQuery?.usedIndexes || []); }}
function relatedNames() {{ const names=new Set(); DATA.relationships.forEach(r=>{{names.add(r.fromTable);names.add(r.toTable)}}); return names; }}
function visibleEntities() {{
  const mode=document.getElementById('groupSelect').value;
  const qTables=queryTables(); const related=relatedNames();
  return DATA.entities.filter(e => mode==='all' || (mode==='query' && qTables.has(e.name)) || (mode==='connected' && related.has(e.name)) || (mode==='junction' && e.junctionCandidate));
}}
function candidateIndex(index, table, columnKeys) {{ return (index.columns || []).some((c,i) => i===0 && columnKeys.has(columnKey(table,c.name))); }}
function layoutPositions(items) {{
  const viewportWidth=Math.max(900, document.getElementById('viewport').clientWidth - 20);
  const cols=Math.max(1, Math.floor(viewportWidth/310)); const gapX=300, gapY=330;
  const positions=new Map(); items.forEach((e,i)=>positions.set(e.name, {{x:20+(i%cols)*gapX,y:20+Math.floor(i/cols)*gapY}}));
  const rows=Math.ceil(items.length/cols); const canvas=document.getElementById('canvas'); canvas.style.width=`${{Math.max(900,cols*gapX+30)}}px`; canvas.style.height=`${{Math.max(700,rows*gapY+40)}}px`; return positions;
}}
function render() {{
  const items=visibleEntities(); const positions=layoutPositions(items); const cards=document.getElementById('cards'); cards.innerHTML='';
  const qTables=queryTables(), qCols=queryColumnKeys(), used=usedIndexes();
  items.forEach(e => {{
    const p=positions.get(e.name); const card=document.createElement('section'); card.className='card'; card.dataset.table=e.name; card.style.left=p.x+'px'; card.style.top=p.y+'px';
    if (activeQuery && qTables.has(e.name)) card.classList.add('query-hit'); else if(activeQuery) card.classList.add('dim');
    const kind=e.kind==='view'?'view':(e.junctionCandidate?'table · junction candidate':'table');
    card.innerHTML=`<h3>${{escapeHtml(e.name)}} <span class="badge">${{escapeHtml(kind)}}</span></h3><div class="section-title">Columns</div><ul class="columns">${{e.columns.map(c=>`<li data-column="${{escapeHtml(c.name)}}" class="${{qCols.has(columnKey(e.name,c.name))?'hit':''}}">${{escapeHtml(c.name)}} <span class="badge">${{escapeHtml(c.type || 'typeless')}}${{c.primaryKeyOrder?' · PK':''}}${{c.notNull?' · NOT NULL':''}}</span></li>`).join('')}}</ul><div class="section-title">Indexes</div><ul class="indexes">${{e.indexes.map(ix=>`<li data-index="${{escapeHtml(ix.name)}}" class="${{used.has(ix.name)?'used ':''}}${{candidateIndex(ix,e.name,qCols)?'candidate':''}}">${{escapeHtml(ix.name)}} <span class="badge">${{ix.unique?'unique':'non-unique'}}${{ix.partial?' · partial':''}}</span></li>`).join('') || '<li class="badge">none</li>'}}</ul>`;
    card.querySelector('h3').addEventListener('click',()=>{{selected={{kind:'table',table:e.name}}; renderDetails();}});
    card.querySelectorAll('[data-column]').forEach(node=>node.addEventListener('click',ev=>{{ev.stopPropagation();selected={{kind:'column',table:e.name,column:node.dataset.column}};renderDetails();}}));
    card.querySelectorAll('[data-index]').forEach(node=>node.addEventListener('click',ev=>{{ev.stopPropagation();selected={{kind:'index',table:e.name,index:node.dataset.index}};renderDetails();}}));
    cards.appendChild(card);
  }});
  requestAnimationFrame(drawEdges); renderDetails();
}}
function drawEdges() {{
  const svg=document.getElementById('edges'); svg.innerHTML=''; const canvas=document.getElementById('canvas'); const base=canvas.getBoundingClientRect(); const qTables=queryTables();
  DATA.relationships.forEach(r=>{{ const a=document.querySelector(`[data-table="${{CSS.escape(r.fromTable)}}"]`); const b=document.querySelector(`[data-table="${{CSS.escape(r.toTable)}}"]`); if(!a||!b) return; const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect(); const line=document.createElementNS('http://www.w3.org/2000/svg','line'); line.setAttribute('x1',ar.left-base.left+ar.width/2); line.setAttribute('y1',ar.top-base.top+ar.height/2); line.setAttribute('x2',br.left-base.left+br.width/2); line.setAttribute('y2',br.top-base.top+br.height/2); line.setAttribute('class','edge'+(activeQuery&&qTables.has(r.fromTable)&&qTables.has(r.toTable)?' active':'')); svg.appendChild(line); }});
}}
function indexDescription(ix) {{ const origin=ix.origin==='pk'?'created for a PRIMARY KEY':ix.origin==='u'?'created for a UNIQUE constraint':'explicitly created'; const cols=(ix.columns||[]).map(c=>c.name+(c.descending?' DESC':'')).join(', '); return `${{ix.unique?'Unique':'Non-unique'}} SQLite index; ${{origin}}${{ix.partial?'; partial index':''}}. Key columns: ${{cols || 'expression/rowid'}}.`; }}
function renderDetails() {{
  const panel=document.getElementById('details'); let out=`<h2>Database evidence</h2><div class="kv"><b>Engine</b><span>${{escapeHtml(DATA.database.engine)}} ${{escapeHtml(DATA.database.sqliteVersion)}}</span><b>File</b><span>${{escapeHtml(DATA.database.path)}}</span></div>`;
  if(activeQuery) {{ out+=`<h3>Active query — ${{escapeHtml(activeQuery.name)}}</h3><pre>${{escapeHtml(activeQuery.sql)}}</pre><h3>Query plan</h3>${{activeQuery.planError?`<p>${{escapeHtml(activeQuery.planError)}}</p>`:''}}<pre>${{escapeHtml((activeQuery.plan||[]).map(p=>p.detail).join('\n') || 'No plan evidence captured.')}}</pre>`; }}
  if(selected) {{ const e=entities.get(selected.table); if(e) {{ if(selected.kind==='table') out+=`<h3>Table — ${{escapeHtml(e.name)}}</h3><p>${{e.junctionCandidate?'This is a junction/associative-table candidate based on multiple foreign keys and limited payload columns. Verify against domain intent.':''}}</p><pre>${{escapeHtml(e.sql || '')}}</pre>`; if(selected.kind==='column') {{ const c=e.columns.find(x=>x.name===selected.column); out+=`<h3>Column — ${{escapeHtml(e.name)}}.${{escapeHtml(c?.name)}}</h3><div class="kv"><b>Type</b><span>${{escapeHtml(c?.type || 'typeless')}}</span><b>Nullable</b><span>${{c?.notNull?'No':'Yes'}}</span><b>Primary key</b><span>${{c?.primaryKeyOrder?'Yes':'No'}}</span></div>`; }} if(selected.kind==='index') {{ const ix=e.indexes.find(x=>x.name===selected.index); if(ix) out+=`<h3>Index — ${{escapeHtml(ix.name)}}</h3><p>${{escapeHtml(indexDescription(ix))}}</p><p><b>Planner evidence:</b> ${{usedIndexes().has(ix.name)?'selected by the active query plan':'not shown as selected by the active query plan'}}</p><pre>${{escapeHtml(ix.sql || 'SQLite autoindex; no CREATE INDEX statement stored.')}}</pre>`; }} }} }}
  panel.innerHTML=out;
}}
render();
</script>
</body>
</html>
"""


def export_workbench(db_path: Path, out_dir: Path, queries_path: Path | None = None) -> tuple[Path, Path]:
    model = build_model(db_path, queries_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "workbench.json"
    html_path = out_dir / "index.html"
    json_path.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    html_path.write_text(render_html(model), encoding="utf-8")
    return html_path, json_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a read-only interactive SQLite learning workbench.")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="Inspect a SQLite database and generate self-contained HTML/JSON learning artifacts.")
    export.add_argument("--db", required=True, type=Path, help="Path to the local development/test SQLite database.")
    export.add_argument("--out", required=True, type=Path, help="Output directory for index.html and workbench.json.")
    export.add_argument("--queries", type=Path, help="Optional JSON array of query objects: name, sql, and optional parameters.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "export":
        html_path, json_path = export_workbench(args.db, args.out, args.queries)
        print(f"Generated: {html_path}")
        print(f"Evidence:  {json_path}")
        return 0
    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
