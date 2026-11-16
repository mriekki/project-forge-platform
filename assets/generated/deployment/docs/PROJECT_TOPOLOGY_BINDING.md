# Project topology target binding

Project Forge keeps reusable non-secret target definitions in the developer's personal profile while each Project owns its logical environment-to-target binding in `DEPLOYMENT_TOPOLOGY.json`.

For an existing environment whose durable intent is already `placement: remote-target`, `adapter: remote-ssh`, and `bindingState: deferred`, Deployment Kit can preview and persist one target binding without rewriting Bootstrap provenance or other topology fields.

## Preview

```text
project-forge-deploy topology plan-binding <environment> \
  --target-profile <logical-target> \
  --root . \
  --json
```

The preview:

- reads the current project-owned topology;
- requires the named environment to already be a remote-target/remote-ssh environment;
- loads the selected user-scoped target profile;
- checks declared target OS compatibility;
- shows the exact before/after environment record;
- changes only `bindingState` and `targetProfile`;
- records a topology hash so a later write fails if the file changed after preview;
- never deploys an application, runs a proof, or changes target SSH/profile state.

A configured environment bound to another target is not eligible for this command. Rebinding requires a separate explicit topology-change contract.

## Apply

```text
project-forge-deploy topology bind <environment> \
  --target-profile <logical-target> \
  --root .
```

The write requires the bounded phrase reported by the plan:

- `[PROJECT TOPOLOGY WRITE]` for non-Production environments;
- `[PROJECT PRODUCTION TOPOLOGY WRITE]` for Production-class environments.

Production classification comes from the existing topology role. The command never infers a Production target and this authorization is only for project configuration; it does **not** authorize Production proof or application deployment.

After a successful write, callers should re-read `DEPLOYMENT_TOPOLOGY.json` and continue normal environment setup/readiness from the selected logical target.
