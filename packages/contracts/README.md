# API contracts

`openapi.json` is the versioned public contract shared by the backend and web application.

Regenerate it after an API schema change:

```powershell
apps/api/.venv/Scripts/python.exe scripts/export_openapi.py
```

CI regenerates the schema and fails when the committed contract is stale.

