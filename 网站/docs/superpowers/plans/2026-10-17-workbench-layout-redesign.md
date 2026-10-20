# Workbench Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restyle and regroup the corrosion research workbench so its research stages, current task, and results are easy to understand without changing computation behavior.

**Architecture:** Keep the existing panel IDs, JavaScript selectors, API calls, and result data contracts. Add only semantic navigation groups and layout markers in `index.html`, then apply a scoped visual layer at the end of `styles.css`; add a small DOM contract test to prevent accidental loss of workflow panels.

**Tech Stack:** HTML, CSS, existing ES modules, Node built-in test runner, real browser screenshots.

## Global Constraints

- Do not alter MATLAB, Python, APDL, Origin, task-directory, input-file, or output-file behavior.
- Keep all existing panel IDs and action IDs intact.
- Keep existing status colors and button semantics.
- Do not overwrite existing task results or the untracked `gcm-diagnose.log`.

---

### Task 1: Add the layout contract test

**Files:**
- Create: `网站/frontend/tests/layout.test.mjs`

- [ ] **Step 1: Write the failing test**

Assert that `index.html` contains the `product-performs` layout marker, three navigation group labels, all eight existing panel IDs, and the new typography tokens in `styles.css`.

- [ ] **Step 2: Run the test and verify it fails**

Run: `node --test frontend/tests/layout.test.mjs` from the `网站` directory.

Expected: FAIL because the current markup has no grouped navigation or layout marker.

### Task 2: Apply semantic layout markers

**Files:**
- Modify: `网站/frontend/index.html`

- [ ] **Step 1: Add `data-layout="product-performs"` to `main` and `data-ui-shell` to `body`.
- [ ] **Step 2: Wrap existing navigation buttons in the three groups `采集与模拟`, `验证与拟合`, and `结果与记录` without changing button IDs, `data-panel`, or accessible names.
- [ ] **Step 3: Add concise current-stage wording to the topbar while preserving `#page-label` and `#sync-button`.
- [ ] **Step 4: Run the layout test and verify it passes.

### Task 3: Implement the visual system

**Files:**
- Modify: `网站/frontend/styles.css`

- [ ] **Step 1: Add scoped design tokens for display, body, helper, surface, ink, accent, warning, spacing, and focus colors.
- [ ] **Step 2: Restyle the sidebar as a grouped process rail, with readable navigation text and a clear active state.
- [ ] **Step 3: Restyle the topbar, hero, section headings, cards, action bars, parameter controls, result previews, and history rows using the new type scale and flat surfaces.
- [ ] **Step 4: Add desktop, tablet, and mobile rules that keep forms readable and prevent horizontal overflow.
- [ ] **Step 5: Run `node --test frontend/tests/layout.test.mjs` and the existing frontend tests.

### Task 4: Browser validation and delivery

**Files:**
- No additional source files unless validation finds a visual defect.

- [ ] **Step 1: Restart the local service through the existing launcher so the updated stylesheet is served.
- [ ] **Step 2: Inspect the desktop home, point-cloud form, simulation form, results page, history page, and the 390px mobile viewport.
- [ ] **Step 3: Verify panel switching, the Origin result preview, the “在 Origin 中继续编辑” button, file download links, and GitHub sync status remain visible and usable.
- [ ] **Step 4: Run `git diff --check`, `node --check` for changed JavaScript, and the complete frontend test command.
- [ ] **Step 5: Commit only the layout files, tests, and design documents; leave `gcm-diagnose.log` untracked.
