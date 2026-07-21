'use client'

import { useEffect, useMemo, useReducer, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { CheckCircle2, GitPullRequest, ShieldCheck } from 'lucide-react'

/* Real pairs from the deterministic hipify pass — not invented for the demo. */
const LINES = [
  { cuda: '#include <cuda_runtime.h>', hip: '#include <hip/hip_runtime.h>' },
  { cuda: '', hip: '' },
  { cuda: 'cudaError_t e = cudaMalloc(&d_a, bytes);', hip: 'hipError_t e = hipMalloc(&d_a, bytes);' },
  { cuda: 'cudaMemcpy(d_a, a, bytes, cudaMemcpyHostToDevice);', hip: 'hipMemcpy(d_a, a, bytes, hipMemcpyHostToDevice);' },
  { cuda: '', hip: '' },
  { cuda: 'cudaStream_t stream;', hip: 'hipStream_t stream;' },
  { cuda: 'cudaStreamCreate(&stream);', hip: 'hipStreamCreate(&stream);' },
  { cuda: 'cudaStreamSynchronize(stream);', hip: 'hipStreamSynchronize(stream);' },
  { cuda: 'cudaFree(d_a);', hip: 'hipFree(d_a);' },
]

const REPOS = [
  { name: 'pytorch/extension-cpp', score: 44 },
  { name: 'NVIDIA/cuda-samples', score: 28 },
  { name: 'cupy/cupy', score: 51 },
  { name: 'Dao-AILab/flash-attention', score: 37 },
]

function tone(score: number) {
  if (score >= 50) return 'text-[#00d4ff] bg-[#00d4ff]/12'
  if (score >= 40) return 'text-[#ffb648] bg-[#ffb648]/12'
  return 'text-[#ff6b87] bg-[#ff365d]/14'
}

function highlight(text: string, changed: boolean, migrated: boolean) {
  if (!text || !changed) return text
  return text.split(/((?:cuda|hip)[A-Za-z_]*|<[^>]+>)/g).filter(Boolean).map((part, i) =>
    /^(cuda|hip)[A-Za-z_]*$/.test(part) || /^<.+>$/.test(part) ? (
      <span
        key={i}
        className={migrated ? 'rounded-[3px] bg-[#7c5cff]/22 px-[3px]' : 'rounded-[3px] bg-[#ff365d]/16 px-[3px]'}
      >
        {part}
      </span>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}

export default function HeroDashboard() {
  const reduced = useReducedMotion()
  const [migrated, bump] = useReducer((n: number) => (n >= LINES.length ? 0 : n + 1), reduced ? LINES.length : 0)
  const [repoIdx, setRepoIdx] = useState(0)

  useEffect(() => {
    if (reduced) return
    const id = setInterval(bump, 420)
    return () => clearInterval(id)
  }, [reduced])

  useEffect(() => {
    if (reduced) return
    const id = setInterval(() => setRepoIdx((i) => (i + 1) % REPOS.length), 2600)
    return () => clearInterval(id)
  }, [reduced])

  const done = migrated >= LINES.length
  const replacements = useMemo(
    () =>
      LINES.slice(0, migrated).reduce(
        (n, l) => (l.cuda === l.hip ? n : n + (l.cuda.match(/cuda[A-Za-z_]*|<[^>]+>/g) || []).length),
        0,
      ),
    [migrated],
  )

  return (
    <div className="relative">
      {/* ambient bloom behind the stack */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-12 -z-10 rounded-full opacity-70 blur-3xl"
        style={{
          background:
            'radial-gradient(38% 44% at 30% 24%, rgba(255,54,93,0.24), transparent 70%), radial-gradient(42% 46% at 76% 74%, rgba(124,92,255,0.20), transparent 72%)',
        }}
      />

      {/* ---------- conversion console ---------- */}
      <motion.div
        initial={{ opacity: 0, y: 26 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.15, ease: [0.22, 0.61, 0.36, 1] }}
        className="glass edge-lit relative overflow-hidden rounded-2xl shadow-[0_36px_90px_-40px_rgba(0,0,0,0.95)]"
      >
        <div className="flex items-center gap-3 border-b border-[var(--color-line)] px-4 py-3">
          <span className="flex gap-1.5" aria-hidden>
            <i className="h-2.5 w-2.5 rounded-full bg-[#ff365d]/60" />
            <i className="h-2.5 w-2.5 rounded-full bg-white/12" />
            <i className="h-2.5 w-2.5 rounded-full bg-white/12" />
          </span>
          <span className="font-mono text-[12.5px] text-[var(--color-ink)]">
            {done ? 'muladd.hip' : 'muladd.cu'}
          </span>
          <span
            className={[
              'rounded px-1.5 py-0.5 text-[9.5px] font-bold tracking-[0.08em] transition-colors duration-300',
              done ? 'bg-[#7c5cff]/18 text-[#b9a6ff]' : 'bg-[#ff365d]/16 text-[#ff6b87]',
            ].join(' ')}
          >
            {done ? 'HIP' : 'CUDA'}
          </span>
          <span className="ml-auto flex items-center gap-2 text-[10.5px] uppercase tracking-[0.06em] text-[var(--color-ink-3)]">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
            hipify · deterministic
          </span>
        </div>

        <div className="py-3 font-mono text-[12.5px] leading-[1.85]">
          {LINES.map((line, i) => {
            const isMig = i < migrated
            const changed = line.cuda !== line.hip
            return (
              <div
                key={i}
                className={[
                  'grid grid-cols-[32px_minmax(0,1fr)] items-baseline pr-3 transition-colors duration-300',
                  isMig && changed ? 'text-[#c9bcff]' : changed ? 'text-[#ff9aad]' : 'text-[var(--color-ink-3)]',
                ].join(' ')}
              >
                <span className="select-none pr-3 text-right text-[10.5px] text-white/20">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <code className="block min-w-0 overflow-hidden text-ellipsis whitespace-pre">
                  {highlight(isMig ? line.hip : line.cuda, changed, isMig)}
                </code>
              </div>
            )
          })}
        </div>

        <div className="border-t border-[var(--color-line)] bg-black/25 px-4 pb-3 pt-2.5">
          <div className="h-[2px] overflow-hidden rounded bg-white/8">
            <span
              className="block h-full origin-left bg-gradient-to-r from-[#ff365d] via-[#7c5cff] to-[#00d4ff] transition-transform duration-300"
              style={{ transform: `scaleX(${migrated / LINES.length})` }}
            />
          </div>
          <div className="mt-2.5 flex items-center gap-2.5 text-[11px] text-[var(--color-ink-3)]">
            <span>
              <strong className="tnum font-semibold text-[var(--color-ink)]">{replacements}</strong> replacements
            </span>
            <i className="h-[3px] w-[3px] rounded-full bg-white/20" />
            <span>
              <strong className="font-semibold text-[var(--color-ink)]">0%</strong> AI
            </span>
            <span
              className={[
                'ml-auto flex items-center gap-1.5 transition-opacity duration-300',
                done ? 'text-[var(--color-success)] opacity-100' : 'opacity-40',
              ].join(' ')}
            >
              <ShieldCheck size={12} aria-hidden />
              hipcc verified
            </span>
          </div>
        </div>
      </motion.div>

      {/* ---------- floating scan card ---------- */}
      <motion.div
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
        className="floaty glass edge-lit absolute -bottom-16 left-0 z-10 w-[220px] sm:w-[246px] rounded-2xl p-3.5 shadow-[0_28px_70px_-34px_rgba(0,0,0,0.95)] sm:-left-16"
      >
        <div className="mb-2.5 flex items-center justify-between text-[10.5px] uppercase tracking-[0.06em]">
          <span className="flex items-center gap-1.5 text-[#ff6b87]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#ff365d]" />
            scanning
          </span>
          <span className="tnum text-[var(--color-ink-3)]">{REPOS.length} repos</span>
        </div>
        <ul className="grid gap-1.5">
          {[0, 1, 2].map((offset) => {
            const repo = REPOS[(repoIdx + offset) % REPOS.length]
            return (
              <li
                key={`${repo.name}-${repoIdx}`}
                className="flex items-center gap-2 rounded-lg bg-white/3 px-2 py-1.5"
                style={{ opacity: 1 - offset * 0.32 }}
              >
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-[var(--color-ink-2)]">
                  {repo.name}
                </span>
                <span className={`tnum rounded px-1.5 py-0.5 text-[11px] font-bold ${tone(repo.score)}`}>
                  {repo.score}
                </span>
              </li>
            )
          })}
        </ul>
      </motion.div>

      {/* ---------- floating PR badge ---------- */}
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.5, ease: [0.22, 0.61, 0.36, 1] }}
        className="floaty-slow glass edge-lit absolute -top-9 right-0 z-20 flex max-w-[210px] sm:max-w-[248px] items-center gap-2.5 rounded-xl px-3.5 py-2.5 shadow-[0_22px_60px_-30px_rgba(0,0,0,0.95)] sm:-right-6"
      >
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--color-success)]/14 text-[var(--color-success)]">
          <GitPullRequest size={15} aria-hidden />
        </span>
        <span className="leading-tight">
          <span className="block text-[12px] font-semibold">Migration PR opened</span>
          <span className="flex items-center gap-1 text-[10.5px] text-[var(--color-ink-3)]">
            <CheckCircle2 size={10} className="text-[var(--color-success)]" aria-hidden />
            10 files · CI green
          </span>
        </span>
      </motion.div>
    </div>
  )
}
