# Deploying ROCmPorter Agent (real, live product)

The app is two parts. They must be deployed to **two different places**:

| Part | What it does | Where it goes | Why |
|------|--------------|---------------|-----|
| `frontend/` | The React UI | **Vercel** | Static site, perfect for Vercel |
| `backend/` | Clones repos, scans for CUDA, generates AI patches | **Render** | Needs a real server + `git`; **cannot run on Vercel** |

> **Why not everything on Vercel?** Vercel runs short-lived serverless functions with no persistent machine, no `git`, and no GPU. The backend runs `git clone` and (optionally) an AI model — that needs a real host. Render's free tier does this. This is also why **Ollama can never run on Vercel** — it needs a persistent server holding a multi-GB model in memory.

---

## Step 1 — Deploy the backend to Render

1. Push this repo to GitHub (it already has the remote `origin`).
2. Go to <https://render.com> → **New +** → **Blueprint**.
3. Pick this repository. Render reads [`render.yaml`](render.yaml) automatically and creates the `rocmporter-api` web service.
4. In the service's **Environment** tab, set the secret values (they are `sync: false`, so Render prompts you):
   - `LLM_API_KEY` — your model provider API key (e.g. an OpenAI or Groq key).
   - `LLM_MODEL` — *optional*, e.g. `gpt-4o-mini`. Leave blank for the provider default.
   - `GITHUB_PAT` — *optional*, only for scanning private repos.
5. `LLM_PROVIDER` is preset to `openai` in `render.yaml`. Change it if you use another provider
   (`groq`, `openrouter`, `together`, `deepseek`, `anthropic`).
6. Deploy. When it's live you'll get a URL like `https://rocmporter-api.onrender.com`.
7. Verify: open `https://rocmporter-api.onrender.com/api/health` → should return `{"status":"ok",...}`.

> Free Render services sleep after inactivity; the first request after a nap takes ~30–50s to wake. That's normal on the free tier.

---

## Step 2 — Point the Vercel frontend at the backend

1. In your Vercel project → **Settings → Environment Variables**, add:
   - **Name:** `VITE_API_BASE_URL`
   - **Value:** your Render URL **with no trailing slash**, e.g. `https://rocmporter-api.onrender.com`
   - Apply to **Production** (and Preview if you want).
2. **Redeploy** the frontend (env vars only take effect on a new build).
3. Make sure the Vercel project's **Root Directory** is `frontend`.

That's it. The live site now runs **real scans** against any public GitHub repo.

---

## Step 3 — (Optional) lock down CORS

By default the backend already allows `*.vercel.app` and localhost. To restrict it to
your exact domain, set on Render:

```
APP_CORS_ORIGINS=https://your-app.vercel.app
```

---

## Local development (unchanged)

```powershell
# Backend (uses local Ollama by default)
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

For local AI patches, keep `LLM_PROVIDER=ollama` and run Ollama with a coding model.
To test the hosted path locally, set `LLM_PROVIDER=openai` and `LLM_API_KEY=...` in `backend/.env`.
