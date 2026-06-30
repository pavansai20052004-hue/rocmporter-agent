const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  })

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
