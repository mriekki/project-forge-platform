# Database Learning Workbench

The Database Learning Workbench is the reusable Project Forge learning contract behind `/db-lab`. It makes database behavior that frameworks and ORMs often hide visible enough to inspect, explain, debug, and defend.

It is project-aware rather than a generic SQL course: use the **current** repository's domain, schema, migrations, ORM mappings, queries, and safe development/test database evidence as the curriculum.

Learning remains optional and never changes engineering delivery state.

## Quick start

Use `/coach` for explanation, adaptive questioning, and gap assessment. Use `/db-lab` when the learning needs concrete database evidence.

```text
/coach database design
/db-lab
/db-lab schema
/db-lab changes <work-item>
/db-lab trace <query/file/symbol>
/db-lab plan <query>
/db-lab debug <symptom/query>
/db-lab migration <migration>
/db-lab interview database
```

Invoking `/db-lab` means **inspect current evidence and show the current view**. The learner should not need to remember to refresh, rebuild, or manually maintain an ER diagram.

Natural-language arguments are preferred over rigid syntax. Examples:

```text
/db-lab show me how Recipes and Ingredients are related
/db-lab changes WI-24
/db-lab trace the EF query used by GetWeeklyMealPlan
/db-lab why is this query scanning MealPlanItems
/db-lab show which indexes this query actually uses
/db-lab walk me through the latest migration without applying it
/db-lab give me a database-design interview based on this domain
```

## Current-by-default artifact lifecycle

Generated workbench HTML/JSON is a disposable projection:

```text
current safe database/repository evidence
→ inspect schema / ORM / migrations / queries
→ build current learning model
→ generate current interactive view
```

The database/repository evidence remains authoritative. An older browser tab is not authoritative. Run the lab again and it produces the current view.

When a previous disposable snapshot is available it may help explain what changed, but never outranks current physical/ORM/migration evidence.

## SQLite interactive workbench

Greenfield consumers that include the Core learning payload receive:

```text
tools/project-forge-db-lab/sqlite-workbench.py
```

The tool is dependency-free Python and opens SQLite databases read-only. It generates a self-contained interactive `index.html` and machine-readable `workbench.json`.

### PowerShell

From the repository root, using a **known safe development/test** SQLite file:

```powershell
Set-Location D:\Projects\<repo>
$out = Join-Path $env:TEMP "project-forge-db-lab"
python .\tools\project-forge-db-lab\sqlite-workbench.py export `
  --db .\.data\app.db `
  --out $out
Start-Process (Join-Path $out "index.html")
```

`.data/app.db` is only an example. Use the actual project development/test database path. Never point the learning tool at Production.

### macOS/Linux

```bash
cd /path/to/repo
out="${TMPDIR:-/tmp}/project-forge-db-lab"
python3 tools/project-forge-db-lab/sqlite-workbench.py export \
  --db .data/app.db \
  --out "$out"
open "$out/index.html" 2>/dev/null || xdg-open "$out/index.html"
```

### Query-to-ERD evidence

Create a disposable query-evidence JSON file from captured or otherwise verified SQL:

```json
[
  {
    "name": "Get weekly meal plan",
    "sql": "SELECT r.Id, r.Name FROM MealPlanItems mpi JOIN Recipes r ON r.Id = mpi.RecipeId WHERE mpi.MealPlanId = :mealPlanId",
    "parameters": {
      "mealPlanId": 42
    }
  }
]
```

Run the workbench with that evidence:

```powershell
$out = Join-Path $env:TEMP "project-forge-db-lab"
python .\tools\project-forge-db-lab\sqlite-workbench.py export `
  --db .\.data\app.db `
  --queries .\tmp\db-lab-queries.json `
  --out $out
Start-Process (Join-Path $out "index.html")
```

Each invocation produces the current view. The query-evidence file and generated workbench stay disposable/local unless the project explicitly chooses a sanitized durable artifact.

## What the interactive viewer shows

The SQLite workbench supports:

- tables and views;
- columns, types, nullability, and primary-key participation;
- foreign-key relationships and delete/update actions;
- indexes, uniqueness, origin, partial-index status, key columns, and stored DDL when available;
- junction-table candidates, clearly labeled as a heuristic rather than domain truth;
- clickable tables, columns, and indexes with a learning/details panel;
- query selection and highlighting of referenced tables;
- relationship-edge highlighting when both related tables participate;
- qualified query-column highlighting when resolvable;
- `EXPLAIN QUERY PLAN` evidence for parameterized `SELECT`/`WITH` queries;
- a distinction between indexes selected by the planner and indexes that are merely plausible candidates/relevant to highlighted columns.

The viewer does not claim to understand arbitrary SQL perfectly. SQL-to-table/column mapping includes heuristic parsing, while planner-selected indexes come from SQLite's own query-plan evidence.

## What to expect from `/db-lab`

A useful session follows evidence rather than guesses:

```text
repository intent
→ ORM model
→ physical schema
→ query / executed SQL
→ query plan
→ indexes / constraints / transaction behavior
→ explanation or exercise
```

Explicitly state which layers were verified and which were inferred.

Where useful, distinguish:

```text
DOMAIN MODEL
ORM MODEL
PHYSICAL MODEL
```

## Change-focused learning

Prompt:

```text
/db-lab changes WI-24
```

Use the accepted/delivered change set plus current database evidence. Explain relevant changes to:

- entities/tables and columns;
- primary/foreign/unique/check constraints;
- nullability and cascade behavior;
- indexes and access paths;
- ORM mappings and translation behavior;
- migrations/DDL and data-safety implications;
- query paths;
- transactions/concurrency.

A changed entity/migration/query file proves that database-related code was touched. It does **not** by itself prove that the physical database changed. Verify the physical layer when safe evidence is available.

A good learning summary connects the change to its consequence:

```text
added relationship
→ new FK/invariant
→ new join/access path
→ possible index consideration
→ migration/data compatibility question
```

## Entity Framework to raw SQL

For EF Core, connect:

```text
LINQ / EF expression
→ translation preview such as ToQueryString() when appropriate
→ captured actual DbCommand when available
→ parameters
→ tables and relationships
→ provider query plan
→ indexes selected by the planner
→ result materialization/tracking
```

Translation preview and an actually executed command are different evidence. Label them separately. Use supported logging/interception for executed-command evidence; the SQLite workbench consumes captured SQL and does not replace EF command capture.

Apply the same principle to other ORMs using framework-supported mechanisms.

## Query-to-ERD highlighting

For a query touching `MealPlans`, `MealPlanItems`, and `Recipes`, highlight those tables. If both ends of an FK relationship participate, emphasize the edge. Highlight resolvable qualified columns.

If `EXPLAIN QUERY PLAN` says an index was used, mark it **planner selected**. An index whose leading column appears relevant but was not selected can be shown as **candidate/relevant**, never as used.

If the interactive viewer is unavailable, use a temporary Mermaid/text diagram and clearly label the fallback.

## Query-plan debugging

Preferred learning sequence:

```text
show query/access pattern
→ developer predicts plan/index behavior
→ inspect provider-native plan
→ identify scan/search/join evidence
→ developer proposes a change
→ predict changed plan
→ compare safely when a sandbox is available
```

Do not teach "add an index" without connecting it to a concrete access pattern, selectivity/order needs, write cost and plan evidence.

## Migration review

Prompt:

```text
/db-lab migration AddRecipeRatings
```

Connect:

```text
migration intent
↔ migration/ORM operations
↔ generated SQL/DDL when available
↔ schema before
↔ schema after
↔ data-safety concerns
```

Useful questions:

- Is existing data compatible with a new non-null column?
- Is a backfill required?
- Does a uniqueness constraint match the invariant?
- Is a table rebuild/destructive operation involved?
- What rollback limitations exist?

Do not apply the migration in Database Lab mode.

## Database-design interview

Prompt:

```text
/db-lab interview database
```

Use the project domain for familiarity but perturb requirements so memorizing the schema does not solve the exercise.

Drive:

```text
requirements
→ entities
→ relationships/cardinality
→ keys/constraints
→ normalization
→ access patterns
→ indexes/plans
→ transactions/concurrency
→ evolution/scaling
→ design defense
```

Ask why a junction table exists, why a key was chosen, what deletion means historically, which query justifies an index, which invariant belongs in a database constraint, and what changes under concurrent edits.

## Database competency model

```text
relational modeling
keys + integrity constraints
normalization + data anomalies
SQL query construction
indexes + access patterns
query plans + performance reasoning
transactions + concurrency
ORM translation + abstraction leaks
schema evolution + migrations
database debugging
design defense + interview communication
```

Use L1-L6 per competency rather than one undifferentiated SQL score.

## Cross-lab learning

System Lab owns system context; Database Lab owns database depth.

```text
/system-lab runtime checkout
→ identify Orders DB
→ /db-lab trace <order query>

/db-lab plan <query>
→ database evidence looks healthy but end-to-end latency is high
→ /system-lab performance checkout
```

## Delivery-completion visibility

Successful delivery may visibly recommend:

```text
★ /db-lab changes WI-24
  This work changed database structure or behavior.
  Explore affected relationships, queries, indexes, constraints, and ORM behavior.
```

When database-specific evidence was not materially touched, `/db-lab` may still appear as an available option:

```text
○ /db-lab
  Explore the current database schema, relationships, queries, indexes, and ORM behavior.
```

Do not tell the learner to rebuild or refresh a diagram. Current evidence is part of invoking the lab.

After successful merge/default-branch CI, `/deliver` may prepare a disposable SQLite workbench automatically only when the accepted change is DB-relevant, the tool exists, and a safe local development/test SQLite database path is already known. Never guess the path, create/apply migrations, mutate data, or touch Production just to prepare learning output. Failure remains non-blocking.

## Provider / ORM architecture

The workbench stays provider/ORM-adapter oriented rather than application-specific.

```text
Database adapter
  SQLite concrete path
  PostgreSQL / SQL Server / ... future

ORM evidence
  EF Core first concrete path
  Hibernate / SQLAlchemy / ... future

Canonical learning model
  tables
  columns
  constraints
  relationships
  indexes
  queries
  query-plan steps
  migrations

Interactive viewer
  schema navigation
  learning panels
  query-to-ERD highlighting
```

SQLite + EF Core is a first concrete learning path, not a permanent architectural restriction.

## IDE tooling

Database extensions can improve the human exploration loop, but `/db-lab` must not depend on manipulating their UI.

For SQLite projects, Bootstrap may recommend SQLTools plus its SQLite driver so the developer can independently browse/query the same local database. The reusable lab obtains authoritative evidence from repository/framework/provider-supported mechanisms.

## Safety and fallbacks

Database Lab is read-only learning by default.

Do not:

- connect to Production for learning exercises;
- mutate application data;
- apply/revert migrations;
- create/drop indexes;
- change code to prove a point;
- claim an index was used without plan evidence;
- manufacture executed SQL when only ORM source is available.

The SQLite workbench opens the database with SQLite `mode=ro`. Generated HTML/JSON are disposable learning artifacts and should normally go to temp/cache rather than tracked project paths.

If evidence is missing, say so and continue with the strongest safe layer available. A missing database runtime, ORM trace, interactive viewer, or post-delivery artifact should degrade the experience; it should never block learning or engineering delivery.
