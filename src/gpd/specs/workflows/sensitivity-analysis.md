<purpose>
Determine which input parameters most strongly affect output quantities. Compute partial derivatives, condition numbers, and rank parameters by sensitivity. Identifies which measurements or calculations would most improve final results.

Called from gpd:sensitivity-analysis command. Used to prioritize effort: if parameter A contributes 90% of the uncertainty while parameter B contributes 1%, improving the precision of A has 90x the impact of improving B.
</purpose>

<core_principle>
Not all parameters are created equal. In any physics calculation, some inputs dominate the uncertainty of the output while others are essentially irrelevant. Sensitivity analysis answers the question: "If I could improve the precision of one input, which one would reduce the output uncertainty the most?"

**The sensitivity hierarchy:**

1. Which parameters does the result depend on? (Identify)
2. How strongly does it depend on each? (Quantify)
3. Which dependencies are dangerous? (Flag divergences, resonances, critical points)
4. Where should effort be directed? (Rank and recommend)

A result quoted as "E = 3.7 +/- 0.2 eV" is incomplete without knowing what drives that 0.2 eV. Is it the coupling constant? The cutoff? The grid spacing? The approximation order? Without sensitivity analysis, error bars are numbers without actionable meaning.
</core_principle>

<process>

<step name="initialize" priority="first">
Load workspace-bound supporting context first. Sensitivity analysis may use
project data when it exists in the invoking workspace, but it must not silently
reenter a different recent project.

```bash
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse JSON for: `executor_model`, `verifier_model`, `commit_docs`, `parallelization`, `project_exists`, `state_exists`, `roadmap_exists`.

- If `state_exists=true`: extract conventions, active approximations,
  `convention_lock`, parameter definitions, and `intermediate_results`; use
  `GPD/analysis/PARAMETERS.md` as the parameter registry when present.
- If `state_exists=false`: require explicit parameter declarations from the
  user; standalone outputs stay under `GPD/analysis/` and do not mutate
  `STATE.md` or `state.json`.

Resolve authoritative phase-backed persistence only after the target quantity is
known. If the target resolves to a canonical stored result with phase metadata,
or the user explicitly anchors the run to a current-workspace phase, load phase
context explicitly:

```bash
PHASE_INIT=$(gpd --raw init phase-op --include state,config "{phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: phase initialization failed: $PHASE_INIT"
  # STOP; surface the error.
fi
```

Use that follow-up phase init only when the phase number is authoritative for this run. If no authoritative phase context exists, keep `phase_found=false` and treat the run as analysis-only persistence under `GPD/analysis/`.

**Convention verification** (if project exists):

```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — parameter definitions may be inconsistent"
  echo "$CONV_CHECK"
fi
```

**If `phase_found` is false after an explicit phase-backed resolution attempt:** Error -- phase directory not found in the current workspace.
**If no authoritative phase is resolved:** Create `GPD/analysis/` in the invoking workspace only when you are ready to write the standalone/current-workspace report.

</step>

<step name="define_scope">
**Step 1: Define Scope**

Identify the target quantity and the parameters to analyze.

### 1a. Target quantity

Determine what output quantity f we are analyzing the sensitivity of:

- Check `intermediate_results` for computed quantities.
- For canonical target lookup, use `gpd result search`; once a canonical `result_id` is known, use `gpd result show "{result_id}"` for the direct stored-result view before `gpd result deps "{result_id}"` for the recorded upstream dependency chain. Keep `gpd query search` for SUMMARY/frontmatter lookup.
- Use `--target` directly when supplied; otherwise inspect phase SUMMARY.md files for key results.
- If the canonical target resolves to authoritative phase metadata, record `phase_found`, `phase_dir`, `phase_number`, and `phase_slug` before choosing persistence.
- Never recover phase-backed persistence from `${PHASE_ARG:-}`, recent-project state, or a guessed current phase. Phase-backed writes are allowed only after an authoritative current-workspace phase resolution.

```markdown
## Sensitivity Target

**Output quantity:** f = {description of the quantity}
**Expression:** f(p_1, p_2, ..., p_N) = {functional form if known}
**Nominal value:** f_0 = {current best value}
**Location:** {file:line or phase where computed}
```

### 1b. Parameter identification

Identify all input parameters that f depends on:

1. **Physical parameters:** masses, coupling constants, temperatures, fields, lengths
2. **Numerical parameters:** grid sizes, cutoffs, basis sizes, tolerances
3. **Approximation controls:** expansion orders, truncation levels, regime boundaries
4. **Measured inputs:** experimental values used in the calculation

If project state exists, use it for active approximations and controlling
parameters. In standalone mode, require the user to declare any approximations
or validity bounds to analyze.

```markdown
## Parameters

| #   | Parameter | Symbol | Nominal Value | Uncertainty | Source                |
| --- | --------- | ------ | ------------- | ----------- | --------------------- |
| 1   | {name}    | p_1    | {value}       | {delta_p_1} | {where it comes from} |
| 2   | {name}    | p_2    | {value}       | {delta_p_2} | {source}              |
```

If `--params` is specified, restrict analysis to those parameters. Otherwise analyze all identified parameters.
</step>

<step name="choose_method">
**Step 2: Choose Method**

Select the method per parameter and record the reason:

| Method | Use when | Required evidence |
| --- | --- | --- |
| analytical | closed-form `f(p_1,...,p_N)` exists | compute `partial f / partial p_i` from the derivation chain |
| numerical | dependence is only through a pipeline/code path | central finite difference: perturb `p_i` by `+/-delta`, rerun, compute `(f_plus-f_minus)/(2 delta)` |
| combined | some dependencies are analytic and others are computational | table listing the method used for each parameter |

Default to combined when `--method` is omitted. For numerical derivatives, use a
small relative step, record `f_plus`, `f_minus`, and reject steps that leave the
validity domain.
</step>

<step name="compute_sensitivity">
**Step 3: Compute Sensitivity Coefficients**

For each parameter p_i, compute the dimensionless sensitivity coefficient:

```
S_i = (partial f / partial p_i) * (p_i / f)
```

This is the fractional change in the output per fractional change in the input. A sensitivity of S_i = 2 means a 1% change in p_i produces a 2% change in f.

For every parameter record:

| Field | Meaning |
| --- | --- |
| `df_dp` | analytical or finite-difference derivative at the nominal value |
| `S_i` | dimensionless sensitivity |
| `delta_f_i = abs(df_dp) * delta_p` | absolute contribution to output uncertainty |
| `% total` | `delta_f_i / total_uncertainty` |
| boundary check | `S_i` at the validity-range endpoints |

Flag nonlinear behavior when endpoint sensitivities differ from nominal by more
than 50%. Flag divergent sensitivity when `|S| > 100`; likely causes:

| Pattern                         | Likely cause                | Prescription                                                                  |
| ------------------------------- | --------------------------- | ----------------------------------------------------------------------------- |
| S -> infinity at p = p_c        | Critical point or resonance | Analyze the singularity structure; result may need non-perturbative treatment |
| S oscillates rapidly            | Interference or aliasing    | Check for cancellation, increase numerical precision                          |
| S changes sign                  | Extremum in f(p)            | The output is at a maximum or minimum with respect to this parameter          |
| S ~ 1/epsilon for small epsilon | Regularization sensitivity  | The result depends on the regulator -- physics issue, not numerics            |

</step>

<step name="rank_parameters">
**Step 4: Rank Parameters**

Rank by `abs(df_dp * delta_p)` and report cumulative uncertainty share. Then
classify:

| Check | Threshold | Action |
| --- | --- | --- |
| stiff parameter space | max/min `|S| > 100` | focus follow-up effort on the stiff directions |
| null direction | `|S| < 1e-4` | mark parameter as practically irrelevant |
| correlated null | paired sensitivities nearly equal and opposite | record the cancelling combination |

</step>

<step name="approximation_sensitivity">
**Step 5: Analyze Approximation Sensitivity**

If project state exists, analyze each active approximation in the project (read from `GPD/STATE.md`; load structured data via `gpd --raw init progress --include state,config` if needed). In standalone mode, analyze only the approximations or regime boundaries explicitly supplied for the current target:

### 5a. Identify controlling parameters

Each approximation has a controlling parameter that determines its validity:

| Approximation       | Controlling Parameter | Valid When | Breaks When |
| ------------------- | --------------------- | ---------- | ----------- |
| Perturbation theory | coupling g            | g << 1     | g ~ 1       |
| Non-relativistic    | v/c                   | v/c << 1   | v/c ~ 1     |
| Classical limit     | S/hbar                | S >> hbar  | S ~ hbar    |
| Thermodynamic limit | 1/N                   | N >> 1     | N ~ 1       |
| Mean-field          | 1/z (coordination)    | z >> 1     | z ~ 1       |
| Continuum limit     | a/L (lattice/system)  | a << L     | a ~ L       |

### 5b. Boundary sensitivity

For each approximation, compute what happens as the controlling parameter approaches the validity boundary:

```python
def approximation_sensitivity(compute_with_approx, compute_exact_or_next_order,
                               control_param_values):
    """Measure how the result changes as we approach the approximation boundary."""
    results = []
    for val in control_param_values:
        f_approx = compute_with_approx(val)
        f_better = compute_exact_or_next_order(val)

        systematic_error = abs(f_approx - f_better)
        relative_error = systematic_error / abs(f_better) if f_better != 0 else float('inf')

        results.append({
            'control_param': val,
            'f_approx': f_approx,
            'f_better': f_better,
            'systematic_error': systematic_error,
            'relative_error': relative_error,
        })

    return results
```

### 5c. Estimate systematic error from each approximation

For each approximation, estimate the systematic error it introduces:

```python
# For perturbative approximations: error ~ next order term
# For truncation approximations: error ~ first neglected term
# For discretization approximations: error ~ O(h^p) from convergence test

for approx in active_approximations:
    control_value = approx['current_value']
    error_estimate = approx['error_scaling'](control_value)

    print(f"Approximation: {approx['name']}")
    print(f"  Controlling parameter: {approx['control_param']} = {control_value}")
    print(f"  Estimated systematic error: {error_estimate:.6e}")
    print(f"  Relative to result: {error_estimate / abs(f_nominal):.2e}")

    if error_estimate / abs(f_nominal) > 0.01:
        print(f"  WARNING: Approximation error exceeds 1% -- may dominate uncertainty budget")
```

</step>

<step name="generate_output">
**Step 6: Generate Output**

### 6a. Write SENSITIVITY-REPORT.md

```markdown
---
target: { quantity }
date: { YYYY-MM-DD }
parameters_analyzed: { N }
method: { analytical|numerical|combined }
most_sensitive: { parameter name }
least_sensitive: { parameter name }
divergences_found: { count }
status: completed
---

# Sensitivity Analysis Report

## Target Quantity

**Output:** f = {description}
**Nominal value:** f_0 = {value} +/- {uncertainty}
**Location:** {file:line or phase}

## Parameter Sensitivity Ranking

| Rank | Parameter | Symbol | Nominal | \|S_i\| | delta_f_i | % of Total | Cumulative % |
| ---- | --------- | ------ | ------- | ------- | --------- | ---------- | ------------ |
| 1    | {name}    | {sym}  | {value} | {S}     | {delta_f} | {pct}      | {cumul}      |
| 2    | {name}    | {sym}  | {value} | {S}     | {delta_f} | {pct}      | {cumul}      |

## Sensitivity Details

### {Parameter 1} (Rank 1, \|S\| = {value})

- **Dimensionless sensitivity:** S = {value} (a 1% change in {param} produces a {S}% change in f)
- **Sensitivity at nominal:** {value}
- **Sensitivity at lower bound:** {value}
- **Sensitivity at upper bound:** {value}
- **Linearity:** {linear / mildly nonlinear / strongly nonlinear}
- **Divergence risk:** {none / approaching divergence at p = {value}}

{Repeat for each parameter}

## Parameter Space Structure

### Stiff Directions

- Stiffness ratio: {max |S| / min |S|} = {value}
- Most sensitive: {param} (|S| = {value})
- Least sensitive: {param} (|S| = {value})

### Null Directions

{List parameter combinations that do not affect the result}

### Divergence Warnings

{List any parameters where sensitivity diverges, with physical interpretation}

## Approximation Sensitivity

| Approximation | Control Param | Current Value | Boundary Value | Systematic Error | % of Output |
| ------------- | ------------- | ------------- | -------------- | ---------------- | ----------- |
| {name}        | {param}       | {value}       | {boundary}     | {error}          | {pct}       |

## Uncertainty Budget

| Source                | delta_f | % of Total | Reducible?    | How to Reduce  |
| --------------------- | ------- | ---------- | ------------- | -------------- |
| {param 1} uncertainty | {value} | {pct}      | Yes           | {prescription} |
| {param 2} uncertainty | {value} | {pct}      | Yes           | {prescription} |
| {approx 1} systematic | {value} | {pct}      | {yes/limited} | {prescription} |
| Total (quadrature)    | {value} | 100%       |               |                |

## Recommendations

1. **Highest impact improvement:** Reducing uncertainty in {param} by {factor} would reduce output uncertainty by {amount} ({pct}% improvement).
2. **Diminishing returns:** Further improving {param} has minimal effect (|S| < {threshold}).
3. **Critical warnings:** {Any divergence or instability issues to address.}

## Summary

- Parameters analyzed: {N}
- Dominant parameter: {name} (contributes {pct}% of uncertainty)
- Top 3 parameters account for {pct}% of total uncertainty
- Approximation systematics contribute {pct}% of total uncertainty
- Recommended priority: {ordered list of what to improve}
```

Save to:

- If phase-scoped: `${phase_dir}/SENSITIVITY-REPORT.md`
- If not phase-scoped (standalone or analysis-only): `GPD/analysis/sensitivity-{slug}.md`

Resolve `REPORT_PATH` only after the target quantity and any authoritative phase metadata are known:

- If authoritative phase-backed context exists: `REPORT_PATH="${phase_dir}/SENSITIVITY-REPORT.md"`
- Otherwise: `REPORT_PATH="GPD/analysis/sensitivity-{slug}.md"`

Create `GPD/analysis/` only for the standalone/current-workspace branch:

```bash
mkdir -p GPD/analysis
```

Never write standalone/current-workspace sensitivity reports under `GPD/phases/**`.

### 6b. Update state (phase-scoped project mode only)

Only when both `state_exists` and `phase_found` are true should this workflow update `propagated_uncertainties` via the CLI (which properly syncs `STATE.md` and `state.json`):

```bash
gpd uncertainty add "{target quantity}" \
  --value "{nominal_value}" \
  --uncertainty "{total_uncertainty}" --phase "{phase_number}" --method "sensitivity-analysis"
```

Run this for the target quantity and for each parameter whose sensitivity-derived uncertainty is significant. For example, if the analysis covers multiple intermediate quantities:

```bash
# Target quantity
gpd uncertainty add "{symbol}" \
  --value "{f_nominal}" \
  --uncertainty "{delta_f}" --phase "${phase_number}" --method "sensitivity-analysis"

# Dominant parameter contribution (if separately tracked)
gpd uncertainty add "{symbol}_from_{dominant_param}" \
  --value "{delta_f_dominant}" \
  --uncertainty "{delta_f_dominant}" --phase "${phase_number}" --method "sensitivity-analysis"
```

Record the sensitivity ranking and dominant source in `STATE.md` as a research artifact only in that phase-scoped project mode.

If no phase-scoped project context exists, skip all `gpd uncertainty add` calls. The run ends after writing `GPD/analysis/sensitivity-{slug}.md` in the invoking workspace and presenting the results directly.

</step>

<step name="commit_and_present">
**Commit phase-scoped sensitivity analysis artifacts only when both `state_exists` and `phase_found` are true:**

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${REPORT_PATH}" GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "data(phase-${phase_number}): sensitivity analysis - ${TARGET_QUANTITY}" \
  --files "${REPORT_PATH}" GPD/STATE.md
```

If `commit_docs` is disabled, expect the CLI commit bridge to skip the commit cleanly.
Do not run an unconditional standalone docs commit for this workflow.
If the run is not phase-scoped, do not run `gpd pre-commit-check` or `gpd commit`. Leave `GPD/analysis/sensitivity-{slug}.md` in the working tree and present the findings directly.

**Present final results:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > SENSITIVITY ANALYSIS COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**{target quantity}** = {nominal_value} +/- {total_uncertainty}

Parameters analyzed: {N}
Dominant parameter: {name} (contributes {pct}% of uncertainty)
Top 3 parameters account for {cumul_pct}% of total uncertainty

### Key Findings

- {Dominant parameter and its sensitivity coefficient}
- {Divergence warnings if any}
- {Null directions if any}

### Output Files

- `${REPORT_PATH}` -- full sensitivity report
- `GPD/STATE.md` -- updated with uncertainty estimates only when `state_exists=true` and `phase_found=true`

---

## Next Steps

- **Reduce uncertainty:** Improve precision of {dominant parameter} for greatest impact
- **Error propagation:** `gpd:error-propagation` -- trace full error budget through derivation chain
- **Parameter sweep:** `gpd:parameter-sweep` -- map out behavior across parameter range
- **Convergence:** `gpd:numerical-convergence` -- verify numerical error bars at key points

---
```

</step>

</process>

<failure_handling>

- **Divergent sensitivity:** |S_i| exceeds threshold for one or more parameters. This may indicate a critical point, resonance, or ill-conditioned formulation. Flag prominently in the report and recommend non-perturbative treatment or reformulation near the divergence.
- **Missing parameters:** A parameter required for the analysis cannot be found in `STATE.md`, prior artifacts, or phase summaries. Prompt the user for its nominal value and uncertainty. Do not guess values.
- **Numerical instability:** Finite-difference derivatives give inconsistent results at different step sizes. Reduce perturbation fraction, switch to analytical derivatives if possible, or flag the parameter as requiring special treatment.
- **All-zero sensitivities:** Every |S_i| is effectively zero. Either the output does not depend on any of the analyzed parameters (check the dependency chain for errors), or the perturbation is too small to register (increase delta_frac). Investigate before reporting.

</failure_handling>

<success_criteria>

- [ ] Current-workspace supporting context loaded via `gpd --raw init progress --include state,config --no-project-reentry`
- [ ] `gpd --raw init phase-op` used only when authoritative phase context exists
- [ ] Target quantity identified with nominal value and current uncertainty
- [ ] All relevant input parameters cataloged with nominal values and uncertainties
- [ ] Sensitivity method chosen (analytical, numerical, or combined) and justified
- [ ] Dimensionless sensitivity coefficient S_i computed for each parameter at nominal values
- [ ] Sensitivity evaluated at validity boundary values for each parameter
- [ ] Divergent or anomalously large sensitivities flagged with physical interpretation
- [ ] Parameters ranked by contribution to output uncertainty
- [ ] Stiff directions in parameter space identified (large sensitivity ratio)
- [ ] Null directions identified (parameter combinations with no effect)
- [ ] Active approximations analyzed for systematic error contribution
- [ ] Complete uncertainty budget constructed with dominant source identified
- [ ] SENSITIVITY-REPORT.md generated with ranked parameter table and recommendations
- [ ] `propagated_uncertainties` updated via `gpd uncertainty add` when `state_exists=true` and `phase_found=true`
- [ ] Phase-scoped artifacts committed via `gpd commit`; standalone or analysis-only runs present results directly without `STATE.md` or `state.json` mutations
- [ ] User presented with key findings and next steps

</success_criteria>
