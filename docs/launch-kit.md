# ROCmPorter Launch Kit

Everything needed to launch this project publicly, in order. Do Phase 1 today; do Phase 3 on a single chosen day (Tuesday–Thursday, around 8–10 AM US Eastern = 5:30–7:30 PM IST works well for Hacker News and Reddit).

---

## Phase 1 — Make the repo findable (15 minutes, do first)

Right now the GitHub repo has **no description, no topics, no homepage, and no license shown**. Nobody can find it by searching, and visitors who do land on it see an anonymous hackathon folder. Fix with:

```powershell
gh repo edit pavansai20052004-hue/AMD_HACKTHON `
  --description "Scan any GitHub repo for CUDA/NVIDIA lock-in and get an AMD ROCm readiness report with evidence, risk scores, and verified patch suggestions. Local-first, powered by Ollama." `
  --homepage "https://rocmporter-agent.vercel.app"

gh repo edit pavansai20052004-hue/AMD_HACKTHON `
  --add-topic rocm --add-topic cuda --add-topic amd --add-topic gpu `
  --add-topic hip --add-topic code-migration --add-topic developer-tools `
  --add-topic static-analysis --add-topic ollama --add-topic llm `
  --add-topic fastapi --add-topic react
```

Then in the GitHub web UI:

1. **Settings → Social preview** — upload `docs/screenshots/02-sample-findings.png` (or a 1280×640 crop). This is the image shown when anyone shares the repo link on X, LinkedIn, Slack, Discord. Without it, shares look dead.
2. **Your profile → Customize pins** — pin this repo so it is the first thing visitors see.
3. Commit and push the new `LICENSE` and README so the license badge and hero image go live.

### Strongly consider renaming the repo

`AMD_HACKTHON` (with the typo) tells nobody what the project does. `rocmporter-agent` matches your Vercel domain and is searchable. GitHub auto-redirects the old URL and git remotes after a rename.

```powershell
gh repo rename rocmporter-agent -R pavansai20052004-hue/AMD_HACKTHON
```

**Caveats before renaming:**
- The GitHub Pages mirror URL changes to `.../rocmporter-agent/` — update the README link after.
- If the hackathon submission portal has the old URL, either update the submission or wait until judging is over. The redirect means old links still work, but check the hackathon rules first.

---

## Phase 2 — Prepare the assets (1–2 hours)

1. **Record a 30–60 second GIF or video** of the flow: paste repo URL → findings appear → Generate Patch → verification receipt → export. Use ScreenToGif (free, Windows) or OBS. Put the GIF at the top of the README. A moving demo is the single highest-converting asset a repo can have.
2. **Make sure the Vercel demo's "Load Sample Scan" works flawlessly** — that is where every visitor will click first. Test it on your phone too.
3. Optional: a short dev.to / Hashnode post — "I built a tool that scans repos for CUDA lock-in — here's what I learned about porting to ROCm." Technical war stories convert readers into stargazers.

---

## Phase 3 — Launch day (post all of these the same morning)

Concentrated attention is what creates trending: GitHub Trending ranks by **stars gained in the window**, so 150 stars in one day beats 300 spread over a month. Post everything below within a few hours of each other, then spend the rest of the day replying to every single comment fast — responsiveness visibly drives the second wave.

### Hacker News — "Show HN" (highest potential)

Post at <https://news.ycombinator.com/submit>. Title options (pick one, keep it plain — HN hates hype):

> Show HN: Scan a repo for CUDA lock-in and get an AMD ROCm porting report

URL: the GitHub repo (not the Vercel demo — HN convention for Show HN of open source).

First comment (post immediately after submitting, from your account):

> Hi HN — I built this for an AMD hackathon and kept going. It scans a GitHub repo with deterministic static-analysis rules for CUDA/NVIDIA assumptions (nvcc-only build scripts, CUDAExtension, NVIDIA base images, cupy imports), cites file+line evidence, and scores ROCm portability. A local LLM via Ollama drafts single-file patch diffs, which are syntax-checked and risk-scored before export — the tool deliberately refuses to auto-apply anything without a verification receipt, because LLM patches to build systems are exactly where silent breakage lives.
>
> Live demo (sample mode, nothing to install): https://rocmporter-agent.vercel.app
>
> Honest limitations: verified artifacts today are review bundles, not apply-ready migrations. I'd love feedback on the detection rules — if you have a repo where it misses CUDA usage, that's a test case I want.

### Reddit (each community, tailored — do NOT copy-paste the same text)

- **r/ROCm** — most receptive audience. Title: "I built an open-source tool that scans repos for CUDA assumptions and generates a ROCm readiness report (with local-LLM patch drafts)". Include screenshots, link demo + repo.
- **r/LocalLLaMA** — angle: "Using Ollama + qwen2.5-coder to draft CUDA→ROCm patches, with a verification layer so the LLM can't ship broken diffs". This community loves local-first LLM tooling.
- **r/AMD** — check the subreddit's self-promo rules first (they are strict). Frame as "made a free open-source tool for the ROCm ecosystem", not self-promo.
- Read each subreddit's rules before posting; some require flair or have promo days.

### X / Twitter thread

> 🧵 GPU code is locked to CUDA everywhere — build scripts, Dockerfiles, python deps. I built an open-source agent that scans any repo and tells you exactly what blocks an AMD ROCm port, with file+line evidence.
>
> [attach the demo GIF]
>
> 2/ It doesn't just detect — a local LLM (Ollama) drafts patch diffs, then a verification layer syntax-checks, risk-scores, and diff-replays them. No verification receipt → no export. LLMs don't get to silently break your build.
>
> 3/ 100% local-first: FastAPI + React + Ollama. No cloud GPU, no API keys needed. Try the live sample demo: rocmporter-agent.vercel.app
>
> 4/ Built for the AMD hackathon, MIT-licensed, and I want it to get better: if it misses CUDA usage in your repo, file an issue — every miss becomes a test case. ⭐ github.com/pavansai20052004-hue/AMD_HACKTHON

Tag `@AMD` / ROCm-related accounts only if the content genuinely concerns them (it does here). Use hashtags sparingly: #ROCm #CUDA #opensource.

### LinkedIn (the hackathon story angle)

> I spent [X weeks] building ROCmPorter Agent for the AMD hackathon — an open-source tool that scans any GitHub repo for CUDA lock-in and produces an AMD ROCm readiness report with verified patch suggestions. The hardest part wasn't the LLM — it was building the verification layer that stops the LLM from shipping broken patches. Live demo + code below. Feedback very welcome.

### AMD ecosystem

- Post in the AMD Developer Community forums (community.amd.com) and any hackathon Discord/Slack.
- If the hackathon has a showcase or newsletter, submit to it.

---

## What NOT to do (this kills repos)

- **Never buy stars or join star-exchange rings.** GitHub detects fake-star patterns, removes them, and flagged repos are excluded from Trending — the opposite of the goal. Every star-farm "service" is a scam against you.
- **No mass-DM or comment-spam promotion.** Communities ban it and the reputation damage is permanent.
- **Don't dribble posts out over weeks.** One coordinated day beats a month of trickle for trending math.
- **Don't argue with critics on launch day.** "Good point, filed as an issue" earns more stars than any rebuttal.

## Realistic expectations

- #1 on GitHub Trending overall in a day typically takes 500–1000+ stars in 24h — that's front-page-of-HN territory, which nobody can guarantee.
- **Trending in a language or topic category** (Python, or the `rocm` topic) is genuinely achievable with 100–300 stars in a day from a good HN/Reddit run.
- A well-executed launch for a real tool like this typically lands 50–500 stars. That's the difference between invisible and credible — and it compounds: stars → search ranking → more stars.
