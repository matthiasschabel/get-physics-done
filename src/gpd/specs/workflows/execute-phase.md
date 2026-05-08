<purpose>
Compatibility index for the staged execute-phase workflow.
</purpose>

<stage_authority_split>
Do not load this root file as eager authority for any execute-phase stage. The command wrapper and stage manifest start at `workflows/execute-phase/phase-bootstrap.md`; later stages load only the stage-specific authorities named by `staged_loading.eager_authorities`.

Stage authorities:

- `phase_bootstrap` -> `workflows/execute-phase/phase-bootstrap.md`
- `phase_classification` -> `workflows/execute-phase/phase-classification.md`
- `wave_planning` -> `workflows/execute-phase/wave-planning.md`
- `pre_execution_specialists` -> `workflows/execute-phase/pre-execution-specialists.md`
- `wave_dispatch` -> `workflows/execute-phase/wave-dispatch.md`
- `checkpoint_resume` -> `workflows/execute-phase/checkpoint-resume.md`
- `aggregate_and_verify` -> `workflows/execute-phase/aggregate-and-verify.md`
- `closeout` -> `workflows/execute-phase/closeout.md`
</stage_authority_split>

<compatibility_note>
Use this file only to discover the staged authority map. Runtime behavior is owned by the stage files above and by `workflows/execute-phase-stage-manifest.json`.
</compatibility_note>
