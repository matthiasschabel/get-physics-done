<purpose>
Create executable PLAN.md files for a phase through staged authorities. This root file is an index only; active instructions live in the stage files below.
</purpose>

<process>

## Staged Authority Index

Load exactly one active stage authority at a time from `plan-phase-stage-manifest.json`. The command wrapper starts with `workflows/plan-phase/phase-bootstrap.md`; later stages must be loaded from `staged_loading.eager_authorities` after re-running `gpd --raw init plan-phase "$PHASE" --stage <stage_id>`.

| Order | Stage id | Active authority | Purpose | Next stage |
| ---: | --- | --- | --- | --- |
| 1 | `phase_bootstrap` | `workflows/plan-phase/phase-bootstrap.md` | Phase lookup, contract-gate validation, lifecycle gate, dirty-worktree safety, and bootstrap routing. | `research_routing` |
| 2 | `research_routing` | `workflows/plan-phase/research-routing.md` | Research reuse/refresh/gap routing, researcher handoff, researcher return handling, and numerical planning guard. | `planner_authoring` |
| 3 | `planner_authoring` | `workflows/plan-phase/planner-authoring.md` | Existing-plan handling, planner template rendering, planner handoff, child artifact gate, planner return, and planner checkpoint handling. | `checker_revision` |
| 4 | `checker_revision` | `workflows/plan-phase/checker-revision.md` | Checker handoff, structured checker routing, partial approval, revision loop, and final status. | none |

## Shared Lifecycle Semantics

- Preserve the manifest stage ids, required init fields, allowed tools, write scopes, produced state, checkpoints, and next-stage routing.
- After every staged init reload, parse only fields listed in `INIT.staged_loading.required_init_fields`; do not reuse shell variables parsed from an older stage.
- The bootstrap stage remains read-only and must not eagerly load later stage authorities, runtime delegation, planner templates, contract schema templates, or UI branding.
- Proof-bearing work remains fail-closed: `--skip-verify` and checker-disabled configuration do not waive checker review or an equivalent main-context audit.
- Dirty project worktrees, contract-gate failures, lifecycle-gate failures, and state/scope conflicts stop before research, planning, checking, or writes.

</process>
