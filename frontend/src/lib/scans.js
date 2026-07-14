import { supabase } from './supabase'

// Persist a completed scan to the user's history. Best-effort; never throws.
export async function saveScan(userId, report, repoUrl) {
  if (!supabase || !userId || !report) return
  const summary = report.summary ?? {}
  try {
    await supabase.from('scans').insert({
      user_id: userId,
      repo_url: repoUrl,
      repo_name: report.repo?.name ?? repoUrl?.replace('https://github.com/', '') ?? null,
      score: typeof summary.score === 'number' ? summary.score : null,
      risk_level: summary.riskLevel ?? null,
      findings_count: Array.isArray(report.findings) ? report.findings.length : 0,
    })
  } catch {
    /* history is non-critical; ignore write failures */
  }
}

// Fetch the user's recent scans, newest first.
export async function listScans(userId) {
  if (!supabase || !userId) return []
  const { data } = await supabase
    .from('scans')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(50)
  return data ?? []
}
