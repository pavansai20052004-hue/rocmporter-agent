# 🚀 ROCmPorter Launch Kit

Everything below is ready to paste. Links: app `https://rocmporter-agent.vercel.app` · repo `https://github.com/pavansai20052004-hue/rocmporter-agent`.

---

## 0) Pre-launch checklist (do the night before)

- [ ] **Warm the backend** — open the app and run one scan so Render is awake (free tier sleeps).
- [ ] **⚠️ Consider Render's paid tier ($7/mo) for launch week** — the free tier has cold starts (~40s) and low capacity; if you go viral, scans will time out and you'll lose the crowd. This is the single biggest risk.
- [ ] **GitHub repo → About (gear icon):**
  - Description: `Scan any repo for CUDA lock-in and auto-migrate it to AMD ROCm — evidence-backed, with one-click migration PRs.`
  - Website: `https://rocmporter-agent.vercel.app`
  - Topics: `rocm` `cuda` `amd` `gpu` `hip` `migration` `pytorch` `devtools` `fastapi` `react` `llm` `open-source`
- [ ] **Pin the repo** on your GitHub profile.
- [ ] Confirm the **demo GIF** loads in the README.
- [ ] Have a **screenshot of a real Migration PR** ready to reply with when people ask "does it actually work?"
- [ ] Star your own repo; ask 5–10 friends to star in the first hour (velocity matters for GitHub Trending).

---

## 1) GitHub Trending strategy (how "#1 repo of the day" actually works)

GitHub Trending ranks by **star velocity** (stars gained in a short window), not total stars. To trend:
1. **Concentrate stars into a few hours** — don't drip them over days. Post everywhere the same morning.
2. **Post where developers are** at the same time (HN + Reddit + Twitter + PH).
3. Every post drives people to the repo → the demo GIF converts them → they star.
4. Ask (once, genuinely) for a star in your posts and README.

Best day: **Tuesday–Thursday**. Best time: **~8–10am ET** (US morning + EU afternoon = ~6–7:30pm IST).

---

## 2) Hacker News — "Show HN"

**Title** (HN is strict: no hype words, ≤ 80 chars):
```
Show HN: ROCmPorter – scan a repo for CUDA lock-in and auto-migrate it to AMD
```

**URL:** `https://rocmporter-agent.vercel.app`

**First comment (post immediately after submitting):**
```
Hi HN, I built ROCmPorter to solve a problem I kept hitting: a huge amount of GPU
code is locked to NVIDIA CUDA (nvcc in the build, cudaMalloc in kernels, torch.cuda
everywhere), and porting it to AMD ROCm means reading the whole repo by hand.

ROCmPorter scans any GitHub repo, flags every CUDA/NVIDIA dependency with the exact
file + line as evidence, scores its ROCm readiness (0–100), and can open a pull
request that migrates the flagged files to ROCm/HIP.

How it works:
- Deterministic static analysis finds the CUDA assumptions (no LLM guessing here)
- A hosted LLM drafts the ROCm/HIP patches, which are syntax-checked + diff-replayed
- One click pushes a branch and opens a PR on your repo

It's free for public-repo scans (no signup). Stack: FastAPI + React, Supabase auth,
pluggable LLM provider. There's also a GitHub Action that comments readiness on PRs.

Honest limitations: AI patches need human review before merging, and the free-tier
backend can be slow on a cold start. Feedback very welcome — especially CUDA patterns
it misses.

Repo: https://github.com/pavansai20052004-hue/rocmporter-agent
```

> HN tips: reply to every comment fast and humbly. Don't ask for upvotes (bannable). Don't use a link shortener.

---

## 3) Reddit

### r/ROCm  (most on-target)
**Title:** `I built a tool that scans repos for CUDA lock-in and auto-migrates them to ROCm`

**Body:**
```
I kept running into CUDA-only code that would've run fine on AMD with some porting,
so I built ROCmPorter.

Paste any GitHub repo → it flags every CUDA/NVIDIA dependency with the exact file and
line, gives a ROCm readiness score, and can open a pull request that migrates the
flagged files to ROCm/HIP.

Free for public repos, no signup: https://rocmporter-agent.vercel.app
Open source (MIT): https://github.com/pavansai20052004-hue/rocmporter-agent

It uses static analysis to find the CUDA (not an LLM), then an LLM for the patches
with syntax + diff-replay verification. Would love feedback on CUDA patterns it misses,
and whether the migration PRs are useful on real ROCm codebases.
```

### r/MachineLearning  (use the [P] Project flair)
**Title:** `[P] ROCmPorter – scan any repo for CUDA lock-in, get an AMD ROCm migration PR`
*(reuse the r/ROCm body; add a line about using the readiness score to triage which repos are worth porting.)*

> Reddit tips: follow each sub's self-promotion rules, reply to comments, don't post the same minute in multiple subs. r/CUDA and r/AMD are secondary options.

---

## 4) Twitter / X thread

**Tweet 1 (hook + attach the demo GIF):**
```
A huge amount of GPU code is locked to NVIDIA CUDA.

I built ROCmPorter: paste any GitHub repo → it finds every CUDA dependency, scores
its AMD ROCm readiness, and opens a PR that migrates your code.

Free, no signup 👇
https://rocmporter-agent.vercel.app
```

**Tweet 2:**
```
Why it matters: NVIDIA GPUs are expensive and hard to get. AMD (ROCm) is often cheaper
and available — but porting CUDA → ROCm by hand is brutal.

ROCmPorter automates the painful 90%:
🔍 evidence-backed findings (exact file + line)
🤖 verified ROCm/HIP patches
🚀 one-click migration PRs
```

**Tweet 3:**
```
It even ships as a GitHub Action — every PR gets a ROCm readiness comment. Plus a live
README badge.

Open source (MIT), built with FastAPI + React.

⭐ https://github.com/pavansai20052004-hue/rocmporter-agent

Would love your feedback 🙏
```

> Tag/DM: @AMD, @amddevcentral, ROCm/GPU folks. Post ~9am ET.

---

## 5) LinkedIn

```
🚀 I just launched ROCmPorter — a tool that helps you escape CUDA lock-in.

A massive amount of GPU code only runs on NVIDIA CUDA. Moving it to AMD ROCm (often
cheaper and more available) usually means reading the whole codebase by hand.

ROCmPorter automates it: point it at any GitHub repo and it flags every CUDA
dependency with line-level evidence, scores its ROCm readiness, and can open a pull
request that migrates your code — with verification before anything is applied.

✅ Free for public repos, no signup
✅ Open source (MIT)
✅ GitHub Action + readiness badge for CI

Try it: https://rocmporter-agent.vercel.app
Star it: https://github.com/pavansai20052004-hue/rocmporter-agent

Built with FastAPI, React, and a lot of coffee. Feedback welcome! 🙏

#AMD #ROCm #CUDA #GPU #OpenSource #MachineLearning #DevTools
```

---

## 6) Product Hunt

**Name:** ROCmPorter
**Tagline (≤ 60 chars):** `Escape CUDA lock-in — auto-migrate any repo to AMD ROCm`
**Topics:** Developer Tools, Artificial Intelligence, GitHub, Open Source

**Description:**
```
ROCmPorter scans any GitHub repository for NVIDIA/CUDA lock-in, scores its AMD ROCm
readiness with line-level evidence, and opens a pull request that migrates your code to
ROCm/HIP — with verification before anything is applied. Free for public repos, open
source, and it ships as a GitHub Action that comments readiness on every PR.
```

**Maker's first comment:**
```
Hey Product Hunt! 👋 CUDA lock-in keeps GPU code tied to expensive NVIDIA hardware.
ROCmPorter finds every CUDA dependency in a repo, scores how ready it is for AMD ROCm,
and can open a migration PR for you. It's free to scan public repos (no signup) and
open source. I'd love your feedback — especially on CUDA patterns it should catch.
```

> PH tip: launch at **12:01am PT**. Line up friends to *comment* (not just upvote) in the first hour.

---

## 7) One-line pitch (for DMs, comments, bios)

> ROCmPorter scans your code for NVIDIA CUDA lock-in and automatically migrates it to run on cheaper, more-available AMD GPUs — turning a months-long port into minutes.

---

## 8) Launch-day order of operations

1. **Night before:** finish checklist §0. Warm the server. Set GitHub About/topics.
2. **~8:00am ET:** post **Show HN** → immediately add your first comment.
3. **~8:10am ET:** post to **r/ROCm**, then **r/MachineLearning [P]**.
4. **~8:20am ET:** post the **Twitter thread** (with GIF) + **LinkedIn**.
5. **First 2 hours:** reply to EVERY comment fast. Ask friends to star + comment.
6. **Optional:** Product Hunt on its own day (12:01am PT) for a second wave.
7. **All day:** watch Render logs; if scans slow down, that's the traffic — upgrade the dyno.
