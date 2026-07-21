import { useMemo, useState } from 'react'
import { previewMigration, tokenizeLine } from '../lib/hipify'

/**
 * Evidence snippet with an inline CUDA → HIP preview.
 *
 * The scan already knows exactly which lines are the problem; this shows what
 * the deterministic hipify pass would do to them, immediately and with no model
 * involved. It is a preview of the mechanical pass only — the backend still
 * produces anything that lands in a patch or a pull request.
 */
export default function EvidenceSnippet({ snippet, startLine }) {
  const [showHip, setShowHip] = useState(false)

  const { lines, replacements, advisories } = useMemo(() => {
    const raw = (snippet || '').replace(/\s+$/, '')
    const stats = previewMigration(raw)
    return {
      lines: raw.split('\n'),
      replacements: stats.replacements,
      advisories: stats.advisories,
    }
  }, [snippet])

  if (!snippet) return null

  const convertible = replacements > 0

  return (
    <div className={`ev-snip${showHip ? ' is-hip' : ''}`}>
      <div className="ev-snip-bar">
        <span className="ev-snip-lang">{showHip ? 'HIP' : 'CUDA'}</span>

        {convertible ? (
          <span className="ev-snip-count">
            <strong>{replacements}</strong> deterministic {replacements === 1 ? 'replacement' : 'replacements'}
          </span>
        ) : (
          <span className="ev-snip-count is-manual">needs manual review</span>
        )}

        {advisories > 0 ? (
          <span className="ev-snip-advisory" title="Flagged, but no safe mechanical replacement exists">
            {advisories} advisory
          </span>
        ) : null}

        {convertible ? (
          <button
            type="button"
            className="ev-snip-toggle"
            aria-pressed={showHip}
            onClick={() => setShowHip((v) => !v)}
          >
            {showHip ? 'Show CUDA' : 'Preview HIP'}
          </button>
        ) : null}
      </div>

      <pre className="ev-snip-code">
        <code>
          {lines.map((line, i) => (
            <span key={i} className="ev-snip-line">
              {typeof startLine === 'number' ? (
                <span className="ev-snip-ln">{startLine + i}</span>
              ) : null}
              <span className="ev-snip-text">
                {tokenizeLine(line).map((part, j) => {
                  if (part.hip) {
                    return (
                      <mark key={j} className="ev-tok">
                        {showHip ? part.hip : part.text}
                      </mark>
                    )
                  }
                  if (part.advisory) {
                    return (
                      <mark key={j} className="ev-tok is-advisory">
                        {part.text}
                      </mark>
                    )
                  }
                  return <span key={j}>{part.text}</span>
                })}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}
