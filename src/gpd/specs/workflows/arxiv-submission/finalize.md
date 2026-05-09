<purpose>
Present the final arXiv submission checklist after package validation has passed.
</purpose>

<stage_boundary>
This authority starts only after package materialization succeeds or, on resume, after the same arXiv package validator passes without materializing.
</stage_boundary>

<process>
<step name="finalize">
**Create the tarball and present the submission checklist.**

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  FINALIZE_INIT=$(gpd --raw init arxiv-submission --stage finalize -- "$ARGUMENTS")
else
  FINALIZE_INIT=$(gpd --raw init arxiv-submission --stage finalize)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: arxiv-submission finalize init failed: $FINALIZE_INIT"
  exit 1
fi
```

Use `PACKAGE_VALIDATION` from `gpd --raw validate arxiv-package --materialize` as the authoritative tarball proof. If resuming at finalize, run the same validator without `--materialize` before reporting success. Present a final checklist with:

- package path and size
- figure count
- quality score / status, if available
- LaTeX smoke-check status
- bibliography source/material status
- figure compatibility status
- placeholder scan status
- TeX processing compatibility status
- manual submission steps still required

Do not treat prose-only success as complete. The tarball must be under `GPD/publication/${subject_slug}/arxiv/`, the executable arXiv package validator must pass, and manuscript-root / latest-review gates must hold.
</step>

<community_contribution>
After the arXiv package is finalized, mention that public papers can be added to the README.md "Papers Using GPD" list at https://github.com/psi-oss/get-physics-done#papers-using-gpd with a short problem/approach summary, workflow used, and optional key result or figure. This prompt is informational only; do not block the submission workflow on it.
</community_contribution>

</process>
