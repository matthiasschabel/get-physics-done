"""Gemini-owned ordered shell-workflow rewrite registry."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

GEMINI_APPROVED_CONTRACT_PATH = "GPD/.approved-project-contract.json"


@dataclass(frozen=True, slots=True)
class GeminiShellPatch:
    """One ordered Gemini shell-workflow rewrite."""

    id: str
    apply: Callable[[str], str]


def _exact_patch(patch_id: str, old: str, new: str) -> GeminiShellPatch:
    """Return an exact string replacement patch."""

    def _apply(content: str) -> str:
        return content.replace(old, new)

    return GeminiShellPatch(patch_id, _apply)


def _regex_patch(
    patch_id: str,
    pattern: str,
    replacement: str,
    *,
    flags: int = 0,
) -> GeminiShellPatch:
    """Return a regular-expression replacement patch."""
    compiled = re.compile(pattern, flags)

    def _apply(content: str) -> str:
        return compiled.sub(replacement, content)

    return GeminiShellPatch(patch_id, _apply)


_GEMINI_NEW_PROJECT_INIT_REPLACEMENT = """Run the init command as its own shell call in Gemini auto-edit mode. Do not wrap it in `INIT=$(...)` or an `if` block.

```bash
gpd --raw init new-project
```

If the init command fails, stop, surface the error, and do not proceed with the workflow."""
_GEMINI_NEW_PROJECT_INIT_BLOCK_RE = (
    r"```bash\n"
    r"INIT=\$\((?:gpd --raw init new-project(?: --stage [a-z_]+)?)\)\n"
    r"if \[ \$\? -ne 0 \]; then\n"
    r"(?:  .*\n)+?"
    r"fi\n"
    r"```"
)
_GEMINI_SET_PROFILE_BLOCK = """```bash
gpd config ensure-section
INIT=$(gpd --raw init progress --include state,config)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```"""
_GEMINI_SET_PROFILE_REPLACEMENT = """Run these as separate shell calls in Gemini auto-edit mode. Do not combine them into one multi-line shell block.

```bash
gpd config ensure-section
```

Then run:

```bash
gpd config set model_profile "$PROFILE"
```

These commands may only repair `GPD/config.json` and update `GPD/config.json::model_profile`; do not run project init, progress, state sync, or project reentry from `set-profile`."""
_GEMINI_SET_PROFILE_VALIDATE_BLOCK = """```bash
PROFILE="$(printf '%s' "$ARGUMENTS" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
case "$PROFILE" in
  deep-theory|numerical|exploratory|review|paper-writing) ;;
  "")
    echo "ERROR: Missing profile. Valid profiles: deep-theory, numerical, exploratory, review, paper-writing"
    exit 1
    ;;
  *[[:space:]]*)
    echo "ERROR: set-profile accepts exactly one profile argument."
    exit 1
    ;;
  *)
    echo "ERROR: Invalid profile \\"$PROFILE\\". Valid profiles: deep-theory, numerical, exploratory, review, paper-writing"
    exit 1
    ;;
esac
```"""
_GEMINI_SET_PROFILE_VALIDATE_REPLACEMENT = """Validate the single profile argument without a shell call before running persistence commands. Trim surrounding whitespace. Accept exactly one of: `deep-theory`, `numerical`, `exploratory`, `review`, `paper-writing`. If the argument is missing, contains whitespace, or is not in that list, stop and surface the validation error."""
_GEMINI_SET_PROFILE_VALIDATE_BLOCK_RE = (
    r"```bash\n"
    r"PROFILE=\"\$\(printf '%s' \"\$ARGUMENTS\" \| sed 's/\^\[\[:space:\]\]\*//;s/\[\[:space:\]\]\*\$//'\)\"\n"
    r"case \"\$PROFILE\" in\n"
    r"  deep-theory\|numerical\|exploratory\|review\|paper-writing\) ;;\n"
    r"  \"\"\)\n"
    r"    echo \"ERROR: Missing profile\. Valid profiles: deep-theory, numerical, exploratory, review, paper-writing\"\n"
    r"    exit 1\n"
    r"    ;;\n"
    r"  \*\[\[:space:\]\]\*\)\n"
    r"    echo \"ERROR: set-profile accepts exactly one profile argument\.\"\n"
    r"    exit 1\n"
    r"    ;;\n"
    r"  \*\)\n"
    r"    echo \"ERROR: Invalid profile \"\\\$PROFILE\"\. Valid profiles: deep-theory, numerical, exploratory, review, paper-writing\"\n"
    r"    exit 1\n"
    r"    ;;\n"
    r"esac\n"
    r"```"
)
_GEMINI_SET_PROFILE_BLOCK_RE = (
    r"```bash\n"
    r"gpd config ensure-section\n"
    r"(?:#.*\n)*"
    r"INIT=\$\((?:gpd --raw init progress --include state,config(?: --no-project-reentry)?)\)\n"
    r"if \[ \$\? -ne 0 \]; then\n"
    r"(?:  .*\n)+?"
    r"fi\n"
    r"```"
)
_GEMINI_MINIMAL_COMMIT_BLOCK = """```bash
mkdir -p GPD

PRE_CHECK=$(gpd pre-commit-check --files GPD/PROJECT.md GPD/REQUIREMENTS.md GPD/ROADMAP.md GPD/STATE.md GPD/state.json GPD/config.json 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: initialize research project (minimal)" --files GPD/PROJECT.md GPD/REQUIREMENTS.md GPD/ROADMAP.md GPD/STATE.md GPD/state.json GPD/config.json
```"""
_GEMINI_MINIMAL_COMMIT_REPLACEMENT = """Create the directory structure, run the pre-check, then commit everything. In Gemini auto-edit mode, execute each shell command separately rather than pasting the whole block as one command.

```bash
mkdir -p GPD
```

Then run:

```bash
gpd pre-commit-check --files GPD/PROJECT.md GPD/REQUIREMENTS.md GPD/ROADMAP.md GPD/STATE.md GPD/state.json GPD/config.json
```

If the pre-check reports issues or exits non-zero, surface the output and continue to the commit.

```bash
gpd commit "docs: initialize research project (minimal)" --files GPD/PROJECT.md GPD/REQUIREMENTS.md GPD/ROADMAP.md GPD/STATE.md GPD/state.json GPD/config.json
```"""
_GEMINI_HEALTH_BLOCK_REPLACEMENT = """In Gemini auto-edit mode, run health checks as a direct shell call instead of capturing stderr through temp files.

Default read-only check:

```bash
gpd --raw health
```

Only after explicit confirmation for `--fix`:

```bash
gpd --raw health --fix
```

Do not treat a nonzero health exit status as a wrapper failure when the command output parses as the valid report JSON below."""
_GEMINI_CONTRACT_PERSIST_SENTENCE = (
    "Write the exact approved contract JSON to "
    f"`{GEMINI_APPROVED_CONTRACT_PATH}` using file tools, then persist it into `GPD/state.json`:"
)
_GEMINI_CONTRACT_FILE_NOTE = (
    "Do not write `/tmp` intermediates for the approved contract. In Gemini headless auto-edit mode, keep the exact approved JSON in "
    f"`{GEMINI_APPROVED_CONTRACT_PATH}`, then validate and persist from that file using direct `gpd` commands. "
    "Do not stash the approved contract in shell variables, command substitutions, or heredocs."
)

GEMINI_SHELL_WORKFLOW_PATCHES: tuple[GeminiShellPatch, ...] = (
    _regex_patch(
        "new-project-init-block",
        _GEMINI_NEW_PROJECT_INIT_BLOCK_RE,
        _GEMINI_NEW_PROJECT_INIT_REPLACEMENT,
        flags=re.MULTILINE,
    ),
    _exact_patch(
        "set-profile-validation-exact-block",
        _GEMINI_SET_PROFILE_VALIDATE_BLOCK,
        _GEMINI_SET_PROFILE_VALIDATE_REPLACEMENT,
    ),
    _regex_patch(
        "set-profile-validation-regex-block",
        _GEMINI_SET_PROFILE_VALIDATE_BLOCK_RE,
        _GEMINI_SET_PROFILE_VALIDATE_REPLACEMENT,
        flags=re.MULTILINE,
    ),
    _regex_patch(
        "set-profile-init-block",
        _GEMINI_SET_PROFILE_BLOCK_RE,
        _GEMINI_SET_PROFILE_REPLACEMENT,
        flags=re.MULTILINE,
    ),
    _exact_patch(
        "minimal-commit-block",
        _GEMINI_MINIMAL_COMMIT_BLOCK,
        _GEMINI_MINIMAL_COMMIT_REPLACEMENT,
    ),
    _regex_patch(
        "health-tempfile-block",
        r"```bash\n"
        r"HEALTH_ERR=\$\(mktemp\)\n"
        r"if echo \"\$ARGUMENTS\" \| grep -q \"\\-\\-fix\"; then\n"
        r"[\s\S]+?"
        r"fi\n"
        r"HEALTH_STDERR=\$\(cat \"\$HEALTH_ERR\"\)\n"
        r"rm -f \"\$HEALTH_ERR\"\n"
        r"```",
        _GEMINI_HEALTH_BLOCK_REPLACEMENT,
        flags=re.MULTILINE,
    ),
    _regex_patch(
        "pre-check-capture-echo-lines",
        r'(?m)^([ \t]*)PRE_CHECK=\$\((gpd pre-commit-check --files [^\n]+) 2>&1\) \|\| true\n\1echo "\$PRE_CHECK"$',
        (
            r"\1# Gemini auto-edit: run the pre-check as its own shell call.\n"
            r"\1\2\n"
            r"\1# If the pre-check exits non-zero, surface the output and continue."
        ),
    ),
    _exact_patch(
        "contract-validate-stdin",
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract -",
        f"gpd --raw validate project-contract {GEMINI_APPROVED_CONTRACT_PATH}",
    ),
    _exact_patch(
        "contract-persist-stdin",
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd state set-project-contract -",
        f"gpd state set-project-contract {GEMINI_APPROVED_CONTRACT_PATH}",
    ),
    _exact_patch(
        "contract-persist-sentence",
        "Persist the approved contract into `GPD/state.json` from the same stdin payload:",
        _GEMINI_CONTRACT_PERSIST_SENTENCE,
    ),
    _exact_patch(
        "contract-persist-after-validation-sentence",
        "After validation passes, persist the approved contract into `GPD/state.json` from the same stdin payload:",
        _GEMINI_CONTRACT_PERSIST_SENTENCE,
    ),
    _exact_patch(
        "contract-file-note",
        "Do not write `/tmp` intermediates for the approved contract. Prefer piping the exact approved JSON directly to `gpd ... -`. Only write a file if the user explicitly wants a durable saved copy, and if so place it under the project, not an OS temp directory.",
        _GEMINI_CONTRACT_FILE_NOTE,
    ),
    _exact_patch(
        "convention-check-unit-warning-block",
        """```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — unit mismatches between theory and experiment are the #1 source of false discrepancies"
  echo "$CONV_CHECK"
fi
```""",
        """```bash
# Gemini: run convention verification directly.
gpd --raw convention check 2>/dev/null
```""",
    ),
    _exact_patch(
        "convention-check-paper-warning-block",
        """```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — review before writing paper"
  echo "$CONV_CHECK"
fi
```""",
        """```bash
# Gemini: run convention verification directly.
gpd --raw convention check 2>/dev/null
```""",
    ),
    _exact_patch(
        "command-context-validate-conventions-block",
        """```bash
CONTEXT=$(gpd --raw validate command-context validate-conventions "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```""",
        """```bash
# Gemini: run command-context validation directly.
gpd --raw validate command-context validate-conventions "$ARGUMENTS"
```""",
    ),
    _exact_patch(
        "command-context-write-paper-block",
        """```bash
CONTEXT=$(gpd --raw validate command-context write-paper "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```""",
        """```bash
# Gemini: run command-context validation directly.
gpd --raw validate command-context write-paper "$ARGUMENTS"
```""",
    ),
    _exact_patch(
        "paper-quality-capture-block",
        """```bash
QUALITY=$(gpd --raw validate paper-quality --from-project . 2>/dev/null)
```""",
        """```bash
# Gemini: run paper-quality validation directly.
gpd --raw validate paper-quality --from-project . 2>/dev/null
```""",
    ),
    _exact_patch(
        "comparison-pre-check-commit-block",
        """```bash
PRE_CHECK=$(gpd pre-commit-check --files "${COMPARISON_OUTPUT_PATH}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: theory-experiment comparison for {slug}" \
  --files "${COMPARISON_OUTPUT_PATH}"
```""",
        """```bash
# Gemini: run the pre-check directly; inspect output before committing.
gpd pre-commit-check --files "${COMPARISON_OUTPUT_PATH}" 2>&1 || true

gpd commit \
  "docs: theory-experiment comparison for {slug}" \
  --files "${COMPARISON_OUTPUT_PATH}"
```""",
    ),
    _exact_patch(
        "dependency-graph-pre-check-commit-block",
        """```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/DEPENDENCY-GRAPH.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: generate dependency graph" --files GPD/DEPENDENCY-GRAPH.md
```""",
        """```bash
# Gemini: run the pre-check directly; inspect output before committing.
gpd pre-commit-check --files GPD/DEPENDENCY-GRAPH.md 2>&1 || true

gpd commit "docs: generate dependency graph" --files GPD/DEPENDENCY-GRAPH.md
```""",
    ),
    _exact_patch(
        "init-phase-op-block",
        """```bash
INIT=$(gpd --raw init phase-op)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```""",
        """```bash
# Gemini: run initialization directly.
gpd --raw init phase-op
```""",
    ),
    _exact_patch(
        "init-progress-state-roadmap-config-block",
        """```bash
INIT=$(gpd --raw init progress --include state,roadmap,config)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```""",
        """```bash
# Gemini: run initialization directly.
gpd --raw init progress --include state,roadmap,config
```""",
    ),
    _exact_patch(
        "init-progress-state-block",
        """```bash
INIT=$(gpd --raw init progress --include state)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```""",
        """```bash
# Gemini: run initialization directly.
gpd --raw init progress --include state
```""",
    ),
    _exact_patch(
        "init-phase-op-state-config-phase-arg-block",
        """```bash
INIT=$(gpd --raw init phase-op --include state,config "${PHASE_ARG:-}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```""",
        """```bash
# Gemini: run initialization directly.
gpd --raw init phase-op --include state,config "${PHASE_ARG:-}"
```""",
    ),
    _exact_patch(
        "init-progress-state-config-block",
        """```bash
INIT=$(gpd --raw init progress --include state,config)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP — display the error to the user and do not proceed.
fi
```""",
        """```bash
# Gemini: run initialization directly.
gpd --raw init progress --include state,config
```""",
    ),
)


def apply_gemini_shell_workflow_patches(content: str) -> str:
    """Apply Gemini shell-workflow patches in source-preserving order."""
    for patch in GEMINI_SHELL_WORKFLOW_PATCHES:
        content = patch.apply(content)
    return content


__all__ = [
    "GEMINI_APPROVED_CONTRACT_PATH",
    "GEMINI_SHELL_WORKFLOW_PATCHES",
    "GeminiShellPatch",
    "apply_gemini_shell_workflow_patches",
]
