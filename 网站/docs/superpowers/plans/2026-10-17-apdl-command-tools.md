# APDL Command Tools Implementation Plan

> Execute sequentially in this isolated worktree; side-conversation rules prohibit subagents.

**Goal:** Add the four approved tools without altering existing research jobs.

**Architecture:** Three small backend modules reuse JobService uploads, frozen inputs, MAPDL supervision and table loading. One frontend module mounts advanced tools after APDL initialization and in task results. Parameter-generated and custom-command tasks remain explicitly distinct.

**Tech Stack:** Existing Python, NumPy/SciPy, matplotlib, vanilla JavaScript; no new dependencies.

## Global Constraints

- Original default 49-point curve unchanged.
- Source files/results never overwritten; each command revision and comparison has its own directory.
- Explicit units, columns and material strain interpretation; no silent sorting, extrapolation or registration.
- Raw edited commands never inherit automatic physics-validation claims.
- No automatic launch of large existing research tasks.

## Task 1 — Frozen command revisions

- [ ] Write backend/tests/test_apdl_commands.py: create a small parameter-built fixture, edit materials.mac, verify source hash unchanged, run the new build-only job and verify frozen text/diff; reject invalid file and missing include.
- [ ] Run `python -m unittest backend.tests.test_apdl_commands -q` and observe missing functionality.
- [ ] Add backend/apdl_commands.py functions command_snapshot(service,id), check_commands(service,payload), prepare_custom_apdl(service,payload), run_custom_apdl(spec,job_dir,progress).
- [ ] Hook existing apdl_tension preparation/worker route; reuse freeze_apdl_sources for package inputs.
- [ ] Verify build-only path, hash rejection and custom result labels.

## Task 2 — Material import and preview

- [ ] Write backend/tests/test_apdl_materials.py for explicit mapping, percent/Pa conversion, strain subtraction and rejected reordered/nonfinite rows.
- [ ] Add backend/apdl_materials.py using load_table and normalise_options; keep first-zero and 2–100-point validation.
- [ ] Add server routes for shared table inspection and material import.
- [ ] Verify numerical conversion, unchanged input bytes and compatibility with original curve.

## Task 3 — Diagnosis and experimental comparison

- [ ] Write backend/tests/test_apdl_analysis.py with error-log fixtures and known interpolation/units/overlap cases.
- [ ] Add read-only diagnosis plus independently saved comparison reports in backend/apdl_analysis.py.
- [ ] Add bounded server routes, explicit finished-task checks and raw-source copying.
- [ ] Verify diagnostics preserve state and trial comparisons do not overwrite source outputs.

## Task 4 — Browser tools and integration

- [ ] Write frontend/tests/apdl-tools.test.mjs for plot data, draft switching/reset, patch/template structure and result labels.
- [ ] Add frontend/apdl_tools.mjs; mount material upload/preview inside the existing material controls, command editor and comparison/diagnosis inside results.
- [ ] Hook app.js only after result DOM is rendered; bump frontend cache query.
- [ ] Run all APDL backend tests and frontend tests, then browser-run build/edit/restore/save and trial overlay using temporary data.
- [ ] Run optional micro MAPDL validation if solver available; inspect actual files/logs rather than infer success from process exit.
- [ ] Commit only approved feature files, fast-forward into active site checkout if unchanged, refresh desktop entry without stopping research workers, push and verify remote SHA.
