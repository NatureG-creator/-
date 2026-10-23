# Spec — Workbench result library

- **Target:** Add a local result library for browsing, previewing, organizing, and reusing generated files.
- **Inputs:** Existing completed task output files and user-created library folders.
- **Outputs:** Local library folder tree, copied task artifacts with provenance, and importable uploads.
- **Success command:** `node --test frontend/tests/library.test.mjs` plus backend library API tests and live checks on 8560.
- **Base commit:** `61f177e34bc8aa8594499db86c764f5fb8cfb87f`
- **Scope cuts:** No change to simulation/solver numerics; no Sites publishing; library files stay under local runtime storage.
