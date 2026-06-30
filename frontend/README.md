# Frontend

React + Vite interface for ROCmPorter Agent.

## Local development

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Use `VITE_API_BASE_URL` when the API is not being reached through the local Vite proxy.

## Current product surface

- Repository scan and ROCm readiness report
- Evidence snippets with line ranges
- Local Ollama model selector
- Per-evidence single-file patch generation
- Diff preview plus saved patch file path
