# Work-Item Model

Project Forge reasons from the repository's authoritative work-item system rather than requiring one universal artifact hierarchy.

Possible sources include:

```text
Product Brief
Jira Epic
Feature Brief
Engineering Enabler
Jira Story
GitHub Issue
local requirements
ADR
small session context
```

Authority labels:

```text
PRIMARY
SUPPLEMENTAL
REFERENCE
NOT USED
```

Role labels:

```text
PRODUCT CONTEXT
FEATURE CONTEXT
WORK GROUPING
IMPLEMENTABLE REQUIREMENT
TECHNICAL DECISION
```

Product/Feature Brief modes may be:

```text
not-used
read-existing
supplemental-experimental
authoritative
suggest-complex
```

Never assume:

```text
Jira Epic == Feature Brief
```

Possible relationships vary by team: an Epic may be a feature, initiative, technical workstream, or delivery container; one Epic may have no Feature Brief, one brief, or several.

Existing team conventions outrank Project Forge defaults. Do not create a competing local source of truth merely because Project Forge has a template.

## Execution-state views

Editor badges, dashboards, and `/progress` may summarize work-item execution state from current repository evidence, but those views are not additional workflow authorities.

Keep stable work-item IDs and paths unchanged merely to display status. In particular, do not prefix or rename work-item folders with status text or emoji, and do not reuse a brief/requirements `Status:` field for implementation progress when that field already represents requirement maturity or approval.

Prefer derived views over a second tracked status database. When evidence is incomplete, show no status or `NOT EVIDENCED` rather than inventing completion.
