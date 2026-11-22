# Native successor one-use publication and recovery

Default-off pending independent review. The owner first creates a dedicated
non-triggering authorization issue for one reviewed version, exact source
commit, manifest/candidate digest and admission run/attempt. Its immutable
issue ID and issue number are included in the reviewed release selection.
Exactly one selection commit per version is allowed; the actual publication
issue binds its SHA-256 and exact current public main. No new owner issue is
permitted to reuse an authorization. The separate claim job, without OIDC,
rereads the open authorization and complete comment inventory, writes a
durable consumption record, closes the issue and independently rereads the
marker before preflight. Workflow-wide concurrency serializes claims.
Any ambiguity consumes or holds the selection; never rerun publication,
reopen or replace an authorization, rotate selection for the same version,
or issue a second publication request to resolve a failure. Publisher
permits first-attempt execution only and rechecks exact registry absence
and previous latest. Previous native/legacy jobs retain verification-only
paths without OIDC grants. Existing trusted workflow identity is retained.

Keep source and public main frozen from admission through publication and
receipt verification. If the npm command may have succeeded, verify the
registry artifact, signed provenance and historical job/run against the
exact immutable selection. Use verification-only when the original completed
publish step/marker and exact publishing commit can be verified. If registry
state is uncertain, original step or marker is absent, or main advanced,
**HOLD**. No automated republish or replacement authorization. Require
separate independently reviewed operator reconciliation of actual registry
bytes and signed attestation/run and a reviewed verification-only recovery.
Do not fabricate receipt or alignment facts.
