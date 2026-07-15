import { supabase } from './supabase'

// Persist a completed scan (including the full report so it can be reopened
// later). Best-effort; never throws. Falls back to metadata-only if the
// `report` column hasn't been added to the database yet.
export async function saveScan(userId, report, repoUrl) {
  if (!supabase || !userId || !report) return
  const summary = report.summary ?? {}
  const row = {
    user_id: userId,
    repo_url: repoUrl,
    repo_name: report.repo?.name ?? repoUrl?.replace('https://github.com/', '') ?? null,
    score: typeof summary.portabilityScore === 'number' ? summary.portabilityScore : null,
    risk_level: summary.riskLevel ?? null,
    findings_count: Array.isArray(report.findings) ? report.findings.length : 0,
  }
  try {
    const { error } = await supabase.from('scans').insert({ ...row, report })
    if (error) {
      // Older databases without the report column: keep history working.
      await supabase.from('scans').insert(row)
    }
  } catch {
    /* history is non-critical; ignore write failures */
  }
}

// Recent scans, newest first — metadata only (reports are fetched on demand).
export async function listScans(userId) {
  if (!supabase || !userId) return []
  const { data } = await supabase
    .from('scans')
    .select('id,repo_url,repo_name,score,risk_level,findings_count,created_at')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(50)
  return data ?? []
}

// Full saved scan (including the stored report) for the "reopen report" flow.
export async function getSavedScan(id) {
  if (!supabase || !id) return null
  const { data } = await supabase.from('scans').select('*').eq('id', id).maybeSingle()
  return data ?? null
}
