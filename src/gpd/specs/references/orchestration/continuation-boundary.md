# Continuation Boundary

A spawned `task()` run is one-shot. If it cannot finish without user input, human verification, or a decision, it returns a typed `gpd_return.status: checkpoint` envelope and stops. It must not wait for the user, keep the run alive, or expect resume-in-place.

The orchestrator owns the pause: present the checkpoint, collect the response, record durable continuation state when needed, and start a fresh continuation handoff with explicit state plus the user response.

Checkpoint rules: keep domain content in the returned body or extended fields; name files in `files_written` only after they exist; use `files_written: []` when the checkpoint intentionally defers writes. Include durable bounded-segment resume details only when the child prompt explicitly owns that callsite detail; otherwise return child-owned `checkpoint_intent` with the reason, waiting condition, and cursor/gate hints. `checkpoint_intent` is not durable authority until the parent/applicator supplies parent-owned resume context, result/session identifiers, and timestamps, then resolves and persists a bounded segment. If expected artifacts are named, verify them on disk before accepting success or continuing.

Fresh continuation rules: verify resume preconditions, check named artifacts, perform only approved follow-up work, and return a fresh typed `gpd_return` envelope.

Agent prompts should name only domain-specific checkpoint triggers and payloads, then reference this boundary instead of repeating the full protocol.
