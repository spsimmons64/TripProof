// Thin fetch wrapper. The token lives in sessionStorage so closing the tab signs out - a shared
// dispatch-office PC should not stay signed in to a system holding PHI.
const TOKEN = 'tripproof.token'

export const auth = {
  get: () => sessionStorage.getItem(TOKEN),
  set: (t) => sessionStorage.setItem(TOKEN, t),
  clear: () => sessionStorage.removeItem(TOKEN),
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(method, path, body, { raw = false } = {}) {
  const headers = {}
  const token = auth.get()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && path !== '/auth/login') {
    auth.clear()
    window.location.assign('/login')
    throw new ApiError(401, 'Signed out')
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not JSON */ }
    throw new ApiError(res.status, msg)
  }
  return raw ? res : res.json()
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  // Downloads go through fetch (the token is a header, not a cookie), then to a blob URL.
  async download(p, fallbackName) {
    const res = await request('GET', p, undefined, { raw: true })
    const cd = res.headers.get('Content-Disposition') || ''
    const name = /filename="([^"]+)"/.exec(cd)?.[1] || fallbackName
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  },
  async open(p) {
    const res = await request('GET', p, undefined, { raw: true })
    const url = URL.createObjectURL(await res.blob())
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  },
}
