# Task Overlay Loading

Task overlays are spawn-time metadata pointers for child-agent specialization. They are not base agent prompt content and they are not staged init bodies.

## Body-Free Contract

- Stage or spawn payloads may name `selected_task_overlay_ids`, `task_overlay_load_manifest`, and `task_overlay_policy_summary`.
- `task_overlay_load_manifest` entries carry only `overlay_id`, `role`, `path`, `summary`, `portable_path`, and `body_loaded: false`.
- Payloads must not include `overlay_body`, `overlay_bodies`, `overlay_content`, `overlay_markdown`, `overlay_text`, `rendered_overlay_body`, or equivalent rendered overlay text fields.
- String values in staged overlay metadata remain single-line scalars.
- Every selected overlay ID must resolve through `gpd.core.task_overlays`.
- Each selected overlay must be compatible with the child agent role that receives it.

## Loading Rule

The workflow stage that has the branch facts selects overlay IDs. A child agent may read only the overlay paths listed in its own selected metadata block, and only for the task slice where the metadata applies. Unselected overlays stay absent from bootstrap payloads, staged payloads, projected command surfaces, and base agent prompts.

## Initial Metadata IDs

- `executor.proof_bearing` -> `gpd-executor`
- `executor.bounded_segment` -> `gpd-executor`
- `planner.proof_bearing` -> `gpd-planner`
- `checker.proof_obligation` -> `gpd-plan-checker`
- `review.reader.claim_extraction` -> `gpd-review-reader`
- `review.literature.novelty_positioning` -> `gpd-review-literature`
- `review.math.soundness` -> `gpd-review-math`
- `review.physics.interpretation` -> `gpd-review-physics`
- `review.significance.venue_fit` -> `gpd-review-significance`
- `paper_writer.section_results` -> `gpd-paper-writer`
- `paper_writer.section_methods` -> `gpd-paper-writer`
- `paper_writer.section_intro_discussion` -> `gpd-paper-writer`
- `paper_writer.section_abstract_conclusion` -> `gpd-paper-writer`
- `paper_writer.figure_sensitive` -> `gpd-paper-writer`
- `paper_writer.response_pair` -> `gpd-paper-writer`

This file is the current metadata authority. Future overlay body files may be added under an approved reference or template root only after a spawn callsite selects them without expanding all overlay bodies into staged or base prompt surfaces.
