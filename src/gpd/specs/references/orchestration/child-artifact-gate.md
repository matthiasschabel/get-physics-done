# Child Artifact Gate

Use this gate after every spawned child return and before success, downstream routing, state mutation, or phase/task completion. Each callsite supplies child role, expected artifacts, allowed root/suffix/freshness, validators, applicator, and failure route.

- Route on a valid fenced `gpd_return.status`, not headings, prose, runtime status, files, commits, or preexisting artifacts.
- `completed` requires every expected artifact in `gpd_return.files_written`, present on disk, readable, allowed by path/freshness rules, and accepted by validators.
- Durable state, contract, continuation, or lineage effects require the callsite applicator, normally `gpd apply-return-updates`, with `passed: true`.
- When expected artifacts can be expressed as project-local paths/globs, use `gpd validate handoff-artifacts ... --require-status completed` as the default filesystem/return success gate before local validators.
- Files, commits, runtime success, and preexisting artifacts are recovery evidence only; they never prove success without the typed return, artifact checks, validators, and applicator when required.
- Missing/invalid returns, failed artifact checks, failed validators, or failed applicators leave the handoff incomplete. Do not synthesize, patch, or paste a child `gpd_return`; retry or run explicit main-context fallback with its own return.
- `checkpoint` stops the child; the orchestrator presents the checkpoint and starts a fresh continuation handoff.

Callsite shape: child role; expected artifacts; allowed root/suffix/freshness; validators; applicator; failure route.
