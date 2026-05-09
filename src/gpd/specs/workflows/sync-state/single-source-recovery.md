<purpose>
Regenerate the missing state mirror from the backend-selected surviving source.
</purpose>

<process>

<step name="single_source_recovery">
**If exactly one of `state_md_exists` or `state_json_exists` is true:**

Load single-source recovery for the diagnostic context, but do not choose the
recovery source in the prompt. The backend repair command is the source-selection
authority; it uses the recovery-aware state loader, including recovered backup
sources and integrity issues.

```bash
SINGLE_SOURCE_RECOVERY_INIT=$(gpd --raw init sync-state --stage single_source_recovery)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state recovery init failed: $SINGLE_SOURCE_RECOVERY_INIT"
  exit 1
fi
```

Use `single_source_recovery.required_init_fields` from `SINGLE_SOURCE_RECOVERY_INIT`.

Repair the dual-write pair through the tested backend path:

```bash
SYNC_STATE_REPAIR=$(gpd --raw --cwd "$PROJECT_ROOT" state repair-sync)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state repair failed: $SYNC_STATE_REPAIR"
  exit 1
fi
```

Report `source_used`, `integrity_issues`, and `validation_status` from
`SYNC_STATE_REPAIR`, then stop. Do not prompt for a merge decision and do not
run raw JSON or markdown parsing from the prompt.

</step>

</process>
