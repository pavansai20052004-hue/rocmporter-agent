function resolveApiBase() {
  // Runtime override so the hosted demo can point at a tunneled local backend:
  //   https://<pages-url>/?api=https://your-tunnel.trycloudflare.com
  // The value persists in localStorage; clear it with ?api=reset
  try {
    const fromQuery = new URLSearchParams(window.location.search).get('api')
    if (fromQuery === 'reset') {
      window.localStorage.removeItem('rocmporter-api-base')
    } else if (fromQuery) {
      const cleaned = fromQuery.replace(/\/+$/, '')
      window.localStorage.setItem('rocmporter-api-base', cleaned)
      return cleaned
    } else {
      const stored = window.localStorage.getItem('rocmporter-api-base')
      if (stored) {
        return stored
      }
    }
  } catch {}
  return import.meta.env.VITE_API_BASE_URL ?? ''
}

const API_BASE = resolveApiBase()

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
      ...options,
    })
  } catch (error) {
    throw new Error(formatNetworkError(path, error))
  }

  if (!response.ok) {
    let message = 'Request failed'
    try {
      const data = await response.json()
      message = formatApiError(data.detail ?? data.message ?? message)
    } catch {
      message = response.statusText || message
    }
    throw new Error(message)
  }

  return response.json()
}

function formatNetworkError(path, error) {
  if (path.startsWith('/api/ollama')) {
    return 'Local Ollama or the ROCmPorter API is not reachable yet. Start Ollama and the backend, then refresh model status.'
  }
  if (path.includes('/patches')) {
    return 'Patch generation is unavailable because the local backend or model service is not reachable. You can load the sample scan for a no-network demo.'
  }
  if (path.includes('/exports')) {
    return 'Export failed because the backend is not reachable. Start the local API, or use sample mode for a guided demo.'
  }
  if (path.includes('/github-review')) {
    return 'GitHub review generation needs the backend running. No token was sent from the browser.'
  }
  if (path.includes('/scans')) {
    return 'Repository scan could not start. Check the backend server, internet access, and repository URL, or load the sample scan.'
  }
  return error?.message ?? 'The local ROCmPorter API is not reachable.'
}

function formatApiError(detail) {
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item?.msg) {
          const location = Array.isArray(item.loc) ? item.loc.join('.') : item.loc
          return location ? `${location}: ${item.msg}` : item.msg
        }
        return JSON.stringify(item)
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object') {
    return detail.message ?? detail.error ?? JSON.stringify(detail)
  }
  return String(detail)
}

export function getApiUrl(path) {
  return `${API_BASE}${path}`
}

export function getHealth() {
  return request('/api/health')
}

export function createScan(repoUrl) {
  return request('/api/scans', {
    method: 'POST',
    body: JSON.stringify({ repoUrl }),
  })
}

export function getScan(scanId) {
  return request(`/api/scans/${scanId}`)
}

export function getReport(scanId) {
  return request(`/api/scans/${scanId}/report`)
}

export function getOllamaModels() {
  return request('/api/ollama/models')
}

export function getOllamaStatus(model) {
  const query = model ? `?model=${encodeURIComponent(model)}` : ''
  return request(`/api/ollama/status${query}`)
}

export function warmOllamaModel(model) {
  return request('/api/ollama/warm', {
    method: 'POST',
    body: JSON.stringify({ model }),
  })
}

export function createPatch(scanId, payload) {
  return request(`/api/scans/${scanId}/patches`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getPatches(scanId) {
  return request(`/api/scans/${scanId}/patches`)
}

export function getPatch(scanId, patchId) {
  return request(`/api/scans/${scanId}/patches/${patchId}`)
}

export function repairPatch(scanId, patchId) {
  return request(`/api/scans/${scanId}/patches/${patchId}/repair`, {
    method: 'POST',
  })
}

export function verifyPatch(scanId, patchId) {
  return request(`/api/scans/${scanId}/patches/${patchId}/verify`, {
    method: 'POST',
  })
}

export function applyPatch(scanId, patchId) {
  return request(`/api/scans/${scanId}/apply-patch`, {
    method: 'POST',
    body: JSON.stringify({ patchId }),
  })
}

export function getPatchApply(applyId) {
  return request(`/api/patch-applies/${applyId}`)
}

export function rollbackPatchApply(applyId) {
  return request(`/api/patch-applies/${applyId}/rollback`, {
    method: 'POST',
  })
}

export function createExport(scanId, payload) {
  return request(`/api/scans/${scanId}/exports`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createGitHubReview(scanId, payload) {
  return request(`/api/scans/${scanId}/github-review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
