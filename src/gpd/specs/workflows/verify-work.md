<purpose>
Compatibility index for the staged `verify-work` workflow.
</purpose>

<stage_authority_index>
Do not use this index as active stage authority. The command wrapper and staged
manifest `verify-work-stage-manifest.json` load the stage-specific files below:

- `session_router`: `workflows/verify-work/session-router.md`
- `phase_bootstrap`: `workflows/verify-work/phase-bootstrap.md`
- `inventory_build`: `workflows/verify-work/inventory-build.md`
- `interactive_validation`: `workflows/verify-work/interactive-validation.md`
- `gap_repair`: `workflows/verify-work/gap-repair.md`
</stage_authority_index>

<boundary_summary>
`session_router` owns argument parsing, active-session discovery from
`active_verification_sessions`, centralized review preflight, project-contract
visibility, lifecycle gating, and `verification_report_status_payload` handling.
Never shell-loop over `GPD/phases` or call `gpd frontmatter get` for active
verification sessions there.
Read `active_verification_sessions` from `SESSION_ROUTER_INIT`. Route on each
entry's canonical `status` / `routing_status`. Use canonical artifact discovery
helpers during bootstrap.
Never shell-loop over `GPD/phases` or call `gpd frontmatter get` here.
Use canonical artifact discovery helpers during bootstrap.
Route on each entry's canonical `status` / `routing_status`.

Later stages must be loaded with `gpd --raw init verify-work "$PHASE_ARG" --stage
<stage_id>` before their authority is used. Proof-redteam classification and repair
begin at `phase_bootstrap`; verifier handoff and verification-report bridges begin
at `inventory_build`; researcher response capture begins at
`interactive_validation`; planner/checker gap repair and closeout live in
`gap_repair`.

Stage ids, produced-state labels, allowed-tool boundaries, writes, required init
fields, and next-stage routing remain manifest-owned for compatibility.
</boundary_summary>
