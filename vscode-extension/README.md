# ROCmPorter for VS Code

CUDA lock-in, visible as you code — with AMD ROCm/HIP fixes one click away.

- ⚠️ **Inline diagnostics** — every CUDA API (`cudaMalloc`, `cudaMemcpy`, `cublasSgemm`, …) is underlined with its HIP equivalent
- 💡 **Hover** any CUDA call to see the ROCm/HIP mapping
- 🔧 **Quick Fix** (Ctrl+.) — replace a single call, or run **"ROCmPorter: Hipify Current File"** to convert the whole file deterministically
- 🚀 **"ROCmPorter: Scan This Repository"** — opens the [ROCmPorter web app](https://rocmporter-agent.vercel.app) pre-filled with this repo for the full evidence report, readiness score, and one-click migration PRs

## Run it (development)

```bash
cd vscode-extension
code .
# Press F5 → launches an Extension Development Host with ROCmPorter active
```

## Package a VSIX

```bash
npm install -g @vscode/vsce
cd vscode-extension
vsce package        # produces rocmporter-0.1.0.vsix
code --install-extension rocmporter-0.1.0.vsix
```

## Settings

| Setting | Default | |
|---|---|---|
| `rocmporter.diagnostics.enabled` | `true` | Inline CUDA lock-in warnings |
| `rocmporter.appUrl` | `https://rocmporter-agent.vercel.app` | Web app used by *Scan This Repository* |

Part of [ROCmPorter](https://github.com/pavansai20052004-hue/rocmporter-agent) — MIT licensed.
