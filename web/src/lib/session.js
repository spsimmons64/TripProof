import { api, auth } from './api.js'

// Keeping a sign-in alive while somebody is working, and ending it when they are not.
//
// A sign-in used to be a fixed eight hours from the moment it was made, and it ran out wherever it
// happened to be - part-way through booking a trip. Now the server's sign-in lasts an hour, and
// this renews it every few minutes for as long as somebody is using the application: a key, a
// click, a scroll. An hour with nobody at the keyboard and it ends here, on purpose, before the
// server has to refuse anything - a dispatch PC left unattended is a screen full of PHI.
//
// The full-screen map is a window of its own with its own copy of the sign-in (sessionStorage is
// per window). It does not count as activity - a map on a second screen is watched, not used - so
// it lives on the main window's sign-in: every renewal is handed to it, and the moment the main
// window signs out, for whatever reason, the map closes rather than being left open on its own.

const IDLE = 60 * 60 * 1000          // the server's sign-in lifetime (settings.jwt_minutes)
const RENEW = 5 * 60 * 1000          // how often a working session is renewed
const WARN = 2 * 60 * 1000           // asked whether to stay signed in this long before the end
const ACTIVITY = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'mousemove']

const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('tripproof-session') : null
let mapWindow = null

// Whose sign-in a token is: messages are only acted on between windows of the same person, so a
// staff tab launched into a customer's portal never hands its sign-in to somebody else's map.
const whose = (token) => {
  try { return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).sub } catch { return null }
}

export function rememberMap(w) { mapWindow = w }

// Every way out goes through here: the Sign out button, a session that went idle, and a request the
// server refused. The map goes first - closed directly where this window opened it, and told over
// the channel where it was opened before a reload lost the handle.
export function signOut() {
  const me = whose(auth.get() || '')
  channel?.postMessage({ type: 'signout', sub: me })
  try { mapWindow?.close() } catch { /* already gone */ }
  auth.clear()
  window.location.assign('/login')
}

// The main window: watch for work, renew while there is some, ask two minutes before the hour is
// up, and sign out at the hour. `onWarn(true)` when the question should be asked, `false` once
// somebody is back; `stay()` is the Yes.
export function keepAlive({ onWarn = () => {} } = {}) {
  let last = Date.now()
  let renewed = Date.now()
  let warned = false
  const renew = async () => {
    try {
      const { token } = await api.post('/auth/refresh', {})
      auth.set(token)
      renewed = Date.now()
      channel?.postMessage({ type: 'token', token, sub: whose(token) })
    } catch { /* refused: api.js has already signed this window out */ }
  }
  // While the question is on the screen only its answer counts: reaching for No moves the mouse,
  // and that must not answer Yes on the way.
  const touch = () => { if (!warned) last = Date.now() }
  const stay = () => { warned = false; last = Date.now(); onWarn(false); renew() }
  ACTIVITY.forEach((e) => window.addEventListener(e, touch, { passive: true }))
  const tick = async () => {
    const now = Date.now()
    if (now - last >= IDLE) { signOut(); return }
    if (!warned && now - last >= IDLE - WARN) { warned = true; onWarn(true); return }
    if (last > renewed && now - renewed >= RENEW) await renew()
  }
  const timer = setInterval(tick, 15 * 1000)
  return {
    stop: () => {
      clearInterval(timer)
      ACTIVITY.forEach((e) => window.removeEventListener(e, touch))
    },
    stay,
  }
}

// The map window: take each renewal the main window makes, and close when it signs out.
export function followMain() {
  if (!channel) return () => {}
  const on = (e) => {
    const me = whose(auth.get() || '')
    if (!e.data || e.data.sub !== me) return
    if (e.data.type === 'token') auth.set(e.data.token)
    if (e.data.type === 'signout') { auth.clear(); window.close() }
  }
  channel.addEventListener('message', on)
  return () => channel.removeEventListener('message', on)
}
