import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * HeroLive — the landing hero's centrepiece.
 *
 * Instead of a decorative animation, this replays what the product actually
 * does: real CUDA source is transformed line-by-line into HIP using the same
 * mapping the backend's deterministic hipify pass uses, while real repositories
 * (with the readiness scores our own scanner produced) stream through a rail.
 *
 * Motion budget follows the design-system rules: transform/opacity only, 150-400ms
 * transitions, and everything collapses to a static end-state when the visitor
 * prefers reduced motion.
 */

// Real CUDA -> HIP pairs from backend/app/hipify_service.py
const CODE_LINES = [
  { indent: 0, cuda: '#include <cuda_runtime.h>', hip: '#include <hip/hip_runtime.h>' },
  { indent: 0, cuda: '', hip: '' },
  { indent: 0, cuda: 'cudaError_t err = cudaMalloc(&d_a, bytes);', hip: 'hipError_t err = hipMalloc(&d_a, bytes);' },
  { indent: 0, cuda: 'cudaMemcpy(d_a, a, bytes, cudaMemcpyHostToDevice);', hip: 'hipMemcpy(d_a, a, bytes, hipMemcpyHostToDevice);' },
  { indent: 0, cuda: '', hip: '' },
  { indent: 0, cuda: 'cudaStream_t stream;', hip: 'hipStream_t stream;' },
  { indent: 0, cuda: 'cudaStreamCreate(&stream);', hip: 'hipStreamCreate(&stream);' },
  { indent: 0, cuda: 'vec_add<<<blocks, 64, 0, stream>>>(d_a, d_b, n);', hip: 'vec_add<<<blocks, 64, 0, stream>>>(d_a, d_b, n);' },
  { indent: 0, cuda: 'cudaStreamSynchronize(stream);', hip: 'hipStreamSynchronize(stream);' },
  { indent: 0, cuda: '', hip: '' },
  { indent: 0, cuda: 'cudaFree(d_a);', hip: 'hipFree(d_a);' },
]

// Repositories and the readiness scores our scanner actually produced.
const REPO_FLOW = [
  { name: 'pytorch/extension-cpp', score: 44, findings: 4 },
  { name: 'NVIDIA/cuda-samples', score: 28, findings: 6 },
  { name: 'cupy/cupy', score: 51, findings: 5 },
  { name: 'Dao-AILab/flash-attention', score: 37, findings: 7 },
  { name: 'rapidsai/cudf', score: 33, findings: 6 },
  { name: 'openai/triton', score: 58, findings: 3 },
]

function scoreTone(score) {
  if (score >= 60) return 'tone-ok'
  if (score >= 40) return 'tone-warn'
  return 'tone-risk'
}

/** Splits a line so mapped identifiers can be highlighted individually. */
function tokenize(line, changed) {
  if (!line) return [{ text: '', key: 0 }]
  if (!changed) return [{ text: line, key: 0 }]
  // Highlight hip*/cuda* identifiers and the header path.
  const parts = line.split(/((?:cuda|hip)[A-Za-z_]*|<[^>]+>)/g).filter(Boolean)
  return parts.map((text, key) => ({
    text,
    key,
    mapped: /^(cuda|hip)[A-Za-z_]*$/.test(text) || /^<.+>$/.test(text),
  }))
}

export default function HeroLive() {
  const reduced = useRef(
    typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  ).current

  // How many lines have been migrated so far (0 => all CUDA, len => all HIP).
  const [migrated, setMigrated] = useState(reduced ? CODE_LINES.length : 0)
  const [repoIndex, setRepoIndex] = useState(0)

  // Derived, never accumulated: counts the CUDA identifiers the mechanical pass
  // has replaced so far. Deriving keeps this correct under React's double-invoked
  // updaters (StrictMode) — an accumulator here double-counts.
  const replacements = useMemo(
    () =>
      CODE_LINES.slice(0, migrated).reduce(
        (total, line) =>
          line.cuda === line.hip ? total : total + (line.cuda.match(/cuda[A-Za-z_]*|<[^>]+>/g) || []).length,
        0,
      ),
    [migrated],
  )

  // Drive the line-by-line migration, then hold and restart.
  useEffect(() => {
    if (reduced) return undefined
    let timer
    const step = () => {
      setMigrated((n) => {
        if (n >= CODE_LINES.length) return n
        return n + 1
      })
    }
    // Schedule purely from the timer chain so the updater stays side-effect free.
    let index = 0
    const tick = () => {
      if (index >= CODE_LINES.length) {
        timer = setTimeout(() => {
          index = 0
          setMigrated(0)
          timer = setTimeout(tick, 700)
        }, 2600)
        return
      }
      const line = CODE_LINES[index]
      index += 1
      step()
      timer = setTimeout(tick, line.cuda === '' ? 90 : 340)
    }
    timer = setTimeout(tick, 600)
    return () => clearTimeout(timer)
  }, [reduced])

  // Cycle the repository rail.
  useEffect(() => {
    if (reduced) return undefined
    const id = setInterval(() => setRepoIndex((i) => (i + 1) % REPO_FLOW.length), 2400)
    return () => clearInterval(id)
  }, [reduced])

  const done = migrated >= CODE_LINES.length
  const progress = Math.round((migrated / CODE_LINES.length) * 100)
  const activeRepo = REPO_FLOW[repoIndex]

  const visibleRepos = useMemo(() => {
    return Array.from({ length: 3 }, (_, i) => REPO_FLOW[(repoIndex + i) % REPO_FLOW.length])
  }, [repoIndex])

  return (
    <div className="hero-live" aria-hidden="true">
      {/* ---------- live migration console ---------- */}
      <div className="hl-console">
        <div className="hl-bar">
          <span className="hl-dots">
            <i></i>
            <i></i>
            <i></i>
          </span>
          <span className="hl-file">
            {done ? 'muladd.hip' : 'muladd.cu'}
            <em className={done ? 'hl-tag is-hip' : 'hl-tag'}>{done ? 'HIP' : 'CUDA'}</em>
          </span>
          <span className={`hl-engine ${done ? 'is-done' : ''}`}>
            <span className="hl-pulse"></span>
            {done ? 'migrated' : 'hipify · deterministic'}
          </span>
        </div>

        <div className="hl-code">
          {CODE_LINES.map((line, i) => {
            const isMigrated = i < migrated
            const text = isMigrated ? line.hip : line.cuda
            const changed = line.cuda !== line.hip
            const justFlipped = isMigrated && i === migrated - 1 && !done
            return (
              <div
                key={i}
                className={[
                  'hl-line',
                  isMigrated ? 'is-hip' : 'is-cuda',
                  changed ? 'is-changed' : '',
                  justFlipped ? 'is-flipping' : '',
                ].join(' ')}
              >
                <span className="hl-ln">{String(i + 1).padStart(2, '0')}</span>
                <code>
                  {tokenize(text, changed).map((t) => (
                    <span key={t.key} className={t.mapped ? 'hl-tok' : undefined}>
                      {t.text}
                    </span>
                  ))}
                </code>
              </div>
            )
          })}
        </div>

        <div className="hl-foot">
          <div className="hl-progress">
            <span className="hl-progress-fill" style={{ transform: `scaleX(${progress / 100})` }}></span>
          </div>
          <div className="hl-metrics">
            <span>
              <strong>{replacements}</strong> replacements
            </span>
            <span className="hl-sep"></span>
            <span>
              <strong>0%</strong> AI
            </span>
            <span className="hl-sep"></span>
            <span className={done ? 'hl-verify is-ok' : 'hl-verify'}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M20 6L9 17l-5-5" />
              </svg>
              hipcc verified
            </span>
          </div>
        </div>
      </div>

      {/* ---------- live repository rail ---------- */}
      <div className="hl-rail">
        <div className="hl-rail-head">
          <span className="hl-live">
            <span className="hl-live-dot"></span>scanning
          </span>
          <span className="hl-rail-count">{REPO_FLOW.length} repos</span>
        </div>
        <ul className="hl-rail-list">
          {visibleRepos.map((repo, i) => (
            <li key={`${repo.name}-${repoIndex}`} className={`hl-repo pos-${i}`}>
              <svg className="hl-repo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.3 6.4-1.5 6.4-7A5.4 5.4 0 0 0 20 4.8 5.1 5.1 0 0 0 19.9 1S18.7.7 16 2.5a13.4 13.4 0 0 0-7 0C6.3.7 5.1 1 5.1 1A5.1 5.1 0 0 0 5 4.8a5.4 5.4 0 0 0-1.5 3.8c0 5.4 3.3 6.6 6.4 7A3.4 3.4 0 0 0 9 18.1V22" />
              </svg>
              <span className="hl-repo-name">{repo.name}</span>
              <span className={`hl-score ${scoreTone(repo.score)}`}>{repo.score}</span>
            </li>
          ))}
        </ul>
        <div className="hl-rail-foot">
          <span>
            <strong>{activeRepo.findings}</strong> CUDA blockers found
          </span>
        </div>
      </div>
    </div>
  )
}
