# Guided Next Steps

Substantial Project Forge interactions should not end with a vague `Next:` sentence.

Use evidence-backed guidance:

```text
CURRENT STATE
<what is actually known>

RECOMMENDED NEXT STEP
<one action and why>

CHOICES
<only the relevant bounded actions, rendered through host structured choice UI when available>

RECOMMENDED PATH
<only when multiple future steps are useful>
```

For the current choice, follow `INTERACTIVE_SESSION_GUIDE.md`:

- use the host's structured choice UI when available; in VS Code use the native question surface such as `vscode_askQuestions`;
- action menus are normally **single-select** because the developer is choosing one next action;
- use multi-select only when the workflow explicitly permits several simultaneous selections;
- make the recommended choice visible when evidence supports one;
- include `Other / specify` or free-text when the action space may be incomplete;
- keep genuinely open-ended questions open-ended.

A textual numbered menu is only the documented fallback when no structured choice UI is available. Fallback shape:

```text
OPTIONS — TEXT FALLBACK ONLY
1. ... [READ ONLY]
2. ... [MODIFIES DOCS]
3. ... [MODIFIES FILES]
4. ... [GIT + GITHUB WRITE]
5. Stop [NO ACTION]
```

Show only relevant choices.

Standard action labels include:

```text
[READ ONLY]
[MODIFIES DOCS]
[MODIFIES FILES]
[REQUIREMENTS GATE]
[HUMAN ACCEPTANCE]
[GIT WRITE]
[GITHUB WRITE]
[GIT + GITHUB WRITE]
[REMOTE READ ONLY]
[REMOTE WRITE]
[PRODUCTION WRITE]
[NO ACTION]
```

A selected choice authorizes only the bounded action described, except where a skill explicitly defines a continuous session or compound mechanical action.

A manually invoked compound action skill may itself be the bounded authorization for its routine mechanics. `/deliver`, for example, may proceed through safe short-lived-branch setup/recovery, staging, commit, push, PR creation/update, and CI inspection without inserting separate options for each mechanical step. It still stops at its explicit merge/finalize gate and whenever evidence becomes ambiguous or unsafe.

Conversation may continue automatically; consequential decisions remain explicitly gated.
