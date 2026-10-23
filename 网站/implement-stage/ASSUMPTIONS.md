# Assumption Ledger — Workbench result library
<!-- ASK mode: never -->

| ID | Under-determined by the request | Chosen | Class | Source |
|----|--------------------------------|--------|-------|--------|
| A-001 | Where project folders and saved results live | Inside the local workbench runtime, outside the Git checkout | interface | default |
| A-002 | Whether organizing a result moves or copies the task output | Copy into the library and preserve the original task output | semantic | default |
| A-003 | How imported library items are transferred into a workflow | Create a normal temporary upload record, then use existing workflow input validation | interface | default |
| A-004 | How broad automatic workflow routing should be | Offer explicit compatible destinations for supported file types; do not infer scientific meaning | semantic | default |
