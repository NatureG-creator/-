# Build Note — Workbench result library

| Rung | Feature | Acceptance check (ONE command) | Tier | Status |
|------|---------|-------------------------------|------|--------|
| F0 | Library API and persistent folder root | `python -m unittest backend.tests.test_project_library` | MUST | ✅ |
| F1 | Browse/create folders and save task artifacts | `python -m unittest backend.tests.test_project_library` | MUST | ✅ |
| F2 | Preview/download/import files from library | `python -m unittest backend.tests.test_project_library` | MUST | ✅ |
| F3 | Website library interface and workflow handoff | `node --test frontend/tests/library.test.mjs frontend/tests/layout.test.mjs` | MUST | ✅ |

## Run record

- 2026-10-23: Backend project library tests (4) and frontend import mapping/layout tests passed; live 8560, shortcut, and GitHub sync pending.

## Deferred

- Multi-user collaboration and cloud storage are outside the local workbench scope.

## Blockers
