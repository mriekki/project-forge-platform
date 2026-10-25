# Project Forge — Stable ChatGPT Project Instruction

Use this as the small persistent instruction in a ChatGPT coding Project.

```text
This is a Project Forge coding Project.

At the beginning of a Project Forge coding workflow, load the current public Project Forge ChatGPT bootstrap descriptor from:

https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json

Resolve and use the exact immutable contract snapshot referenced by that descriptor for this conversation/session.

Use Project Forge as the platform name, Project as the normal thing I create, and Builder or Developer for the person using it. Treat "New Project: <idea>" as the greenfield discovery trigger and "New Project from: <PROJECT_INPUT.json or existing product source>" as the imported-discovery trigger for the same repository-owned protocol.

For a new Project, follow the exact discovery contract in that snapshot. Do not invent a separate discovery protocol.

For an existing generated Project, treat its repository-owned artifacts, Git history, pull requests, and CI as authoritative current state. The repository is the durable handoff.

Do not add legacy/versioned handoff-file references, component commit SHAs, product requirements, or current Project state to this persistent instruction. Keep those facts in the repositories that own them.

Use the Developer Profile in this ChatGPT Project only for identity, local environment, and personal working/learning preferences. Do not use it as Project state and never store secrets in it.

If the bootstrap descriptor or referenced snapshot cannot be loaded or verified, do not perform consequential Project generation or platform writes using remembered rules.
```

Do not translate retired Lean technical identifiers into the current contract. Current Project Forge repositories, commands, package names, baselines, and `PROJECT_BOOTSTRAP.json` are authoritative.

Once a conversation resolves a snapshot, keep using that exact snapshot for the session unless the human explicitly asks to re-resolve it.
