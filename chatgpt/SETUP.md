# Set up Project Forge in ChatGPT

This is a one-time setup for a Builder's normal Project Forge coding workspace in ChatGPT.

The end state is deliberately small:

```text
one canonical Project Forge Project instruction (same for every Builder)
+
one personal Developer Profile block
```

You do **not** copy platform repositories, long handoff documents, component commit SHAs, product requirements, or current Project state into ChatGPT Project instructions.

## 1. Create a ChatGPT coding Project

Create a Project named something clear, for example:

```text
Project Forge — Coding Projects
```

## 2. Add the canonical Project Forge instruction

Open the current public descriptor:

```text
https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json
```

Follow its `snapshotPath` to the immutable `PROJECT_INSTRUCTIONS.md` and copy the fenced instruction text **verbatim** into the ChatGPT Project instructions.

That canonical instruction is the same for every Project Forge Builder. Do not create per-person forks of it.

When Project Forge advances the stable contract, `chatgpt/current.json` remains the pointer to the current immutable instruction source.

## 3. Append your personal Developer Profile

Immediately after the canonical Project Forge instruction in the same ChatGPT Project instructions field, add this clearly delimited personal block:

```text
--- Project Forge Developer Profile ---
{
  "schemaVersion": 1,
  "githubOwner": "YOUR-GITHUB-USERNAME",
  "operatingSystem": "windows",
  "shell": "powershell",
  "editor": "Visual Studio Code",
  "workspaceRoot": "D:\\Projects",
  "learningEmphasis": "normal",
  "contractChannel": "stable"
}
--- End Project Forge Developer Profile ---
```

Only `schemaVersion` and `githubOwner` are required. Remove optional fields that do not apply instead of inventing values.

Allowed profile values are defined by `USER_PROFILE.schema.json` in the same immutable snapshot. The profile is **personal configuration only**: identity, local environment, and working/learning preference.

Never put passwords, PATs, private SSH keys, access tokens, Production credentials, product requirements, work-item state, commit SHAs, or other Project state in the Developer Profile.

## 4. Verify the one-time ChatGPT setup

Start a chat in that Project and say:

```text
Verify my Project Forge setup.
```

A correct setup should be able to confirm:

- the current public descriptor and immutable snapshot can be resolved;
- the canonical Project Forge instruction is present;
- the Developer Profile has a valid GitHub username and contains no Project state/secrets;
- the Project is ready to begin a Project Forge workflow.

If the public descriptor or immutable snapshot cannot be loaded and verified, consequential Project generation/platform writes must remain blocked rather than falling back to remembered rules.

## 5. Start a Project

When GitHub onboarding says `READY FOR PROJECT FORGE` and ChatGPT setup verification passes, start greenfield discovery with:

```text
New Project: <your idea>
```

For imported discovery from an existing product definition or validated `PROJECT_INPUT.json`, start with:

```text
New Project from: <PROJECT_INPUT.json or existing product source>
```

Project Forge guides discovery before creating anything.

## 6. After generation

```text
clone repository
→ open generated .code-workspace in VS Code
→ README welcome page
→ /setup
→ /progress or /next-step
→ /start-work <ID>
```

A current generated Project configures VS Code to use its `README.md` as the workspace startup page when there is no restored editor state. That README is the single human-facing "welcome / how to get started" front door; you should not need to hunt through several Markdown files before starting setup.

You do not repeat ChatGPT setup for every generated Project. The generated repository is the durable Project handoff and current-state authority.

## If readiness needs recovery

Normal activation verifies readiness automatically after `/accept-project-forge`. If the public contract or App check later needs retrying, use:

```text
/project-forge-doctor
```

That is a troubleshooting path, not a normal per-Project step.
