import {
  ArrowRight,
  Boxes,
  FileCode2,
  GitPullRequest,
  Radar,
  ScrollText,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from 'lucide-react'
import Nav from '@/components/Nav'
import HeroDashboard from '@/components/HeroDashboard'
import Reveal from '@/components/Reveal'
import BrandMark from '@/components/BrandMark'

function GithubGlyph({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 1.5A10.5 10.5 0 0 0 8.68 22c.53.1.72-.23.72-.5v-1.75c-2.92.64-3.54-1.25-3.54-1.25-.48-1.22-1.17-1.55-1.17-1.55-.96-.65.07-.64.07-.64 1.06.08 1.62 1.09 1.62 1.09.94 1.61 2.47 1.15 3.07.88.1-.68.37-1.15.67-1.42-2.33-.27-4.78-1.17-4.78-5.19 0-1.15.41-2.08 1.09-2.82-.11-.27-.47-1.34.1-2.79 0 0 .88-.28 2.88 1.07a10 10 0 0 1 5.24 0c2-1.35 2.88-1.07 2.88-1.07.57 1.45.21 2.52.1 2.79.68.74 1.09 1.67 1.09 2.82 0 4.03-2.46 4.92-4.8 5.18.38.33.71.97.71 1.96v2.9c0 .28.19.61.73.5A10.5 10.5 0 0 0 12 1.5Z" />
    </svg>
  )
}

const APP = 'https://rocmporter-agent.vercel.app'
const REPO = 'https://github.com/pavansai20052004-hue/rocmporter-agent'

const TRUST = [
  { value: '90+', label: 'CUDA APIs mapped' },
  { value: '100%', label: 'Mechanical pass, 0% AI' },
  { value: 'hipcc', label: 'Verified in AMD CI' },
  { value: 'MIT', label: 'Open source' },
]

const STEPS = [
  { icon: Radar, title: 'Repository scan', body: 'Point at any GitHub URL. Deterministic static analysis clones and reads every translation unit, build file and Docker layer.' },
  { icon: FileCode2, title: 'Evidence detection', body: 'Each finding cites the exact file, line and snippet — with a 0–100 ROCm readiness score you can defend in review.' },
  { icon: TerminalSquare, title: 'Patch generation', body: 'A deterministic hipify pass converts the mechanical majority with zero AI. Only the semantic remainder reaches a model, grounded in curated ROCm docs.' },
  { icon: ShieldCheck, title: 'Verification', body: 'Generated HIP is compiled with real hipcc inside AMD’s official ROCm container. Syntax checks, drift detection and diff replay run before anything is applied.' },
  { icon: GitPullRequest, title: 'GitHub pull request', body: 'One click pushes a branch and opens a PR with per-file provenance: what was mechanical, what was AI-assisted, and what still needs you.' },
]

const FEATURES = [
  { icon: Radar, title: 'Evidence-driven scans', body: 'Every finding points at a file, a line and a snippet. Proof you can click, not a confidence score you have to trust.' },
  { icon: Boxes, title: 'Hybrid migration engine', body: 'Deterministic CUDA→HIP mapping runs first and handles most of the work with no model involved. Files it fully converts never touch an LLM.' },
  { icon: ShieldCheck, title: 'Compile-verified output', body: 'CI runs hipcc in AMD’s rocm/dev container on generated HIP. The badge on our README is a real build, not a claim.' },
  { icon: ScrollText, title: 'Docs-grounded AI', body: 'The semantic remainder is grounded in a curated ROCm knowledge base — warp size 64, cuDNN→MIOpen, torch-on-ROCm semantics.' },
  { icon: GitPullRequest, title: 'One-click migration PRs', body: 'Up to 10 files per pull request, with local header context so the model stays consistent across a codebase.' },
  { icon: Sparkles, title: 'VS Code extension', body: 'CUDA lock-in underlined as you type, HIP equivalents on hover, and one-click file hipify without leaving the editor.' },
]

const PLANS = [
  {
    name: 'Free', price: '$0', cadence: 'forever', tagline: 'For trying it on public repositories.',
    features: ['Unlimited public-repo scans', 'Full ROCm readiness reports', 'Migration checklist', 'Offline exports'],
    cta: 'Start free', href: `${APP}/app`, featured: false,
  },
  {
    name: 'Pro', price: '$29', cadence: 'per month', tagline: 'For engineers shipping the migration.',
    features: ['Everything in Free', 'AI single-file ROCm patches', 'One-click migration PRs', 'Verify + safe apply / rollback', 'GitHub PR review artifacts', 'Private repository scanning'],
    cta: 'Upgrade to Pro', href: `${APP}/billing`, featured: true,
  },
  {
    name: 'Enterprise', price: 'Custom', cadence: 'talk to us', tagline: 'For teams porting many repositories.',
    features: ['Everything in Pro', 'CI/CD scan + patch pipelines', 'AMD Developer Cloud validation', 'Shared audit bundles & seats', 'Priority support'],
    cta: 'Contact sales', href: 'mailto:sales@rocmporter.app', featured: false,
  },
]

export default function Home() {
  return (
    <>
      <Nav />

      <main id="top">
        {/* ================= HERO ================= */}
        <section className="mx-auto flex max-w-6xl flex-col gap-20 px-6 pb-24 pt-32 lg:grid lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16 lg:pt-36">
          <div>
            <Reveal immediate>
              <span className="glass inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[12.5px] text-[var(--color-ink-2)]">
                <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
                Compile-verified on the real ROCm toolchain
              </span>
            </Reveal>

            <Reveal immediate delay={0.06}>
              <h1 className="h-display mt-6">
                Break free from{' '}
                <span className="grad-ink">CUDA lock-in</span>.
              </h1>
            </Reveal>

            <Reveal immediate delay={0.12}>
              <p className="body-lg mt-6 max-w-xl">
                ROCmPorter scans any repository, pinpoints every NVIDIA dependency with line-level evidence, and opens
                a pull request that migrates your code to AMD ROCm — verified by <span className="font-mono text-[var(--color-ink)]">hipcc</span> before you merge.
              </p>
            </Reveal>

            <Reveal immediate delay={0.18}>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <a className="btn-primary" href={`${APP}/app`}>
                  Scan your first repo — free
                  <ArrowRight size={17} strokeWidth={2.4} aria-hidden />
                </a>
                <a className="btn-ghost" href={REPO} target="_blank" rel="noreferrer">
                  <GithubGlyph size={17} />
                  View source
                </a>
              </div>
            </Reveal>

            <Reveal immediate delay={0.24}>
              <dl className="mt-12 grid max-w-lg grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4">
                {TRUST.map((t) => (
                  <div key={t.label}>
                    <dt className="font-display tnum text-[26px] font-bold leading-none tracking-[-0.03em]">{t.value}</dt>
                    <dd className="mt-2 text-[12.5px] leading-snug text-[var(--color-ink-3)]">{t.label}</dd>
                  </div>
                ))}
              </dl>
            </Reveal>
          </div>

          <div className="relative pb-16 lg:pb-0 lg:pl-6 lg:pr-4">
            <HeroDashboard />
          </div>
        </section>

        {/* ================= HOW IT WORKS ================= */}
        <section id="how" className="mx-auto max-w-4xl scroll-mt-28 px-6 py-32">
          <Reveal className="text-center">
            <p className="eyebrow">How it works</p>
            <h2 className="h-section mt-4">From CUDA to a merged pull request</h2>
            <p className="body-lg mx-auto mt-5 max-w-2xl">
              Five stages. The deterministic ones run first, so the model only sees what genuinely needs judgment.
            </p>
          </Reveal>

          <ol className="relative mt-20">
            {/* connecting spine */}
            <span
              aria-hidden
              className="absolute left-[27px] top-3 bottom-3 w-px bg-gradient-to-b from-[#ff365d] via-[#7c5cff] to-[#00d4ff] opacity-45"
            />
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <Reveal delay={i * 0.06}>
                  <div className="group relative flex gap-6 pb-16 last:pb-0">
                    <span className="glass relative z-10 grid h-14 w-14 flex-none place-items-center rounded-2xl text-[var(--color-ink)] transition-transform duration-300 group-hover:-translate-y-0.5">
                      <s.icon size={20} strokeWidth={1.8} aria-hidden />
                    </span>
                    <div className="pt-1.5">
                      <span className="eyebrow tnum">Step {String(i + 1).padStart(2, '0')}</span>
                      <h3 className="h-card mt-2">{s.title}</h3>
                      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-[var(--color-ink-2)]">{s.body}</p>
                    </div>
                  </div>
                </Reveal>
              </li>
            ))}
          </ol>
        </section>

        {/* ================= FEATURES ================= */}
        <section id="features" className="mx-auto max-w-6xl scroll-mt-28 px-6 py-32">
          <Reveal className="max-w-2xl">
            <p className="eyebrow">Features</p>
            <h2 className="h-section mt-4">Built to be believed, not just believed in</h2>
            <p className="body-lg mt-5">
              Every claim on this page is something the product can demonstrate on your repository in the next few minutes.
            </p>
          </Reveal>

          <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => (
              <Reveal key={f.title} delay={(i % 3) * 0.06}>
                <article className="card-glow glass edge-lit group h-full rounded-2xl p-7 transition-transform duration-300 hover:-translate-y-1">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/5 text-[var(--color-ink)] transition-transform duration-300 group-hover:scale-105">
                    <f.icon size={19} strokeWidth={1.8} aria-hidden />
                  </span>
                  <h3 className="h-card mt-6">{f.title}</h3>
                  <p className="mt-3 text-[14.5px] leading-relaxed text-[var(--color-ink-2)]">{f.body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ================= PRICING ================= */}
        <section id="pricing" className="mx-auto max-w-6xl scroll-mt-28 px-6 py-32">
          <Reveal className="text-center">
            <p className="eyebrow">Pricing</p>
            <h2 className="h-section mt-4">Free to scan. Pay to ship.</h2>
            <p className="body-lg mx-auto mt-5 max-w-xl">
              Public-repo scanning is unlimited and needs no account. You only pay when you want the migration done for you.
            </p>
          </Reveal>

          <div className="mt-16 grid items-start gap-5 lg:grid-cols-3">
            {PLANS.map((p, i) => (
              <Reveal key={p.name} delay={i * 0.07}>
                <div
                  className={[
                    'relative h-full rounded-2xl p-8 transition-transform duration-300 hover:-translate-y-1',
                    p.featured
                      ? 'glass edge-lit ring-1 ring-[#7c5cff]/40 shadow-[0_36px_90px_-46px_rgba(124,92,255,0.9)]'
                      : 'glass edge-lit',
                  ].join(' ')}
                >
                  {p.featured ? (
                    <span className="absolute -top-3 left-8 rounded-full bg-gradient-to-r from-[#ff365d] to-[#7c5cff] px-3 py-1 text-[10.5px] font-bold uppercase tracking-[0.08em] text-white">
                      Most popular
                    </span>
                  ) : null}

                  <h3 className="h-card">{p.name}</h3>
                  <p className="mt-2 text-[13.5px] text-[var(--color-ink-3)]">{p.tagline}</p>

                  <div className="mt-7 flex items-baseline gap-2">
                    <span className="font-display tnum text-[44px] font-bold leading-none tracking-[-0.04em]">{p.price}</span>
                    <span className="text-[13px] text-[var(--color-ink-3)]">{p.cadence}</span>
                  </div>

                  <a
                    className={p.featured ? 'btn-primary mt-8 w-full justify-center' : 'btn-ghost mt-8 w-full justify-center'}
                    href={p.href}
                  >
                    {p.cta}
                    {p.featured ? <ArrowRight size={16} strokeWidth={2.4} aria-hidden /> : null}
                  </a>

                  <ul className="mt-8 grid gap-3 border-t border-[var(--color-line)] pt-7">
                    {p.features.map((f) => (
                      <li key={f} className="flex items-start gap-2.5 text-[14px] text-[var(--color-ink-2)]">
                        <ShieldCheck
                          size={15}
                          className={p.featured ? 'mt-0.5 flex-none text-[#b9a6ff]' : 'mt-0.5 flex-none text-[var(--color-ink-3)]'}
                          aria-hidden
                        />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ================= CTA ================= */}
        <section className="mx-auto max-w-4xl px-6 pb-32">
          <Reveal>
            <div className="glass edge-lit relative overflow-hidden rounded-3xl px-8 py-16 text-center">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 -z-10 opacity-80"
                style={{
                  background:
                    'radial-gradient(60% 80% at 50% 0%, rgba(255,54,93,0.16), transparent 70%), radial-gradient(50% 70% at 80% 100%, rgba(0,212,255,0.12), transparent 72%)',
                }}
              />
              <h2 className="h-section mx-auto max-w-2xl">Point it at a repository. See what it finds.</h2>
              <p className="body-lg mx-auto mt-5 max-w-lg">
                Free, no signup, and the whole scan takes seconds.
              </p>
              <a className="btn-primary mt-9" href={`${APP}/app`}>
                Scan a repository
                <ArrowRight size={17} strokeWidth={2.4} aria-hidden />
              </a>
            </div>
          </Reveal>
        </section>
      </main>

      {/* ================= FOOTER ================= */}
      <footer className="border-t border-[var(--color-line)]">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <BrandMark size={30} />
              <span className="font-display text-[17px] font-bold tracking-[-0.02em]">ROCmPorter</span>
            </div>
            <p className="mt-4 max-w-xs text-[14px] leading-relaxed text-[var(--color-ink-3)]">
              Evidence-backed CUDA → AMD ROCm migration, verified on the real toolchain.
            </p>
          </div>

          {[
            { title: 'Product', links: [['Scanner', `${APP}/app`], ['Pricing', '#pricing'], ['VS Code extension', `${REPO}/tree/main/vscode-extension`]] },
            { title: 'Developers', links: [['GitHub', REPO], ['ROCm validation', `${REPO}/blob/main/docs/rocm-validation.md`], ['GitHub Action', `${REPO}/blob/main/action.yml`]] },
            { title: 'Legal', links: [['Terms', `${APP}/terms`], ['Privacy', `${APP}/privacy`]] },
          ].map((col) => (
            <div key={col.title}>
              <p className="eyebrow">{col.title}</p>
              <ul className="mt-5 grid gap-3">
                {col.links.map(([label, href]) => (
                  <li key={label}>
                    <a className="nav-link text-[14px]" href={href}>
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-t border-[var(--color-line)]">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-7 text-[13px] text-[var(--color-ink-3)]">
            <span>© 2026 ROCmPorter · MIT licensed</span>
            <span className="flex items-center gap-2">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
              All systems operational
            </span>
          </div>
        </div>
      </footer>
    </>
  )
}
