import { useMemo } from 'react'
import { previewMigration } from '../lib/hipify'

/**
 * Triage strip above the findings list.
 *
 * A report tells you how many problems exist, but not how much of it is real
 * work. This splits the evidence into what the deterministic pass can convert
 * outright versus what genuinely needs a human, so the shape of the migration
 * is visible before you scroll through it.
 */
export default function FindingsSummary({ findings }) {
  const stats = useMemo(() => {
    let auto = 0
    let manual = 0
    let replacements = 0

    for (const finding of findings ?? []) {
      for (const entry of finding.evidence ?? []) {
        const { replacements: n } = previewMigration(entry.snippet || '')
        if (n > 0) {
          auto += 1
          replacements += n
        } else {
          manual += 1
        }
      }
    }
    return { auto, manual, replacements, total: auto + manual }
  }, [findings])

  if (!stats.total) return null

  const autoPct = Math.round((stats.auto / stats.total) * 100)

  return (
    <section className="fs-strip" aria-label="Migration triage summary">
      <div className="fs-head">
        <p className="section-label">Migration triage</p>
        <span className="fs-total">
          {stats.total} evidence {stats.total === 1 ? 'site' : 'sites'}
        </span>
      </div>

      <div className="fs-bar" role="img" aria-label={`${stats.auto} convert deterministically, ${stats.manual} need review`}>
        {stats.auto > 0 ? <span className="fs-seg is-auto" style={{ width: `${autoPct}%` }} /> : null}
        {stats.manual > 0 ? <span className="fs-seg is-manual" style={{ width: `${100 - autoPct}%` }} /> : null}
      </div>

      <ul className="fs-legend">
        <li>
          <i className="is-auto" />
          <strong>{stats.auto}</strong> convert deterministically
          {stats.replacements > 0 ? <em>
              {stats.replacements} {stats.replacements === 1 ? 'replacement' : 'replacements'}, 0% AI
            </em> : null}
        </li>
        <li>
          <i className="is-manual" />
          <strong>{stats.manual}</strong> need review
          <em>build config, cuDNN, torch paths</em>
        </li>
      </ul>
    </section>
  )
}
