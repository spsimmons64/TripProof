import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, Bell, CheckCheck, ChevronDown, Info, LogOut, ShieldCheck, XCircle } from 'lucide-react'
import { api } from '../lib/api.js'
import { signOut } from '../lib/session.js'
import { Modal } from '../admin/common.jsx'
import TimeZoneSelect from './TimeZoneSelect.jsx'

const POLL_MS = 60000
const LEVEL_ICON = { bad: XCircle, warn: AlertTriangle, info: Info }

// A bell that only draws itself can be missed by somebody reading a different part of the screen,
// and the things that arrive at this level - a driver broken down on the way to a pickup - are
// exactly the ones nobody may miss. Two short notes, synthesised rather than fetched so there is
// no asset to ship and nothing to fail at the moment it is needed.
//
// Browsers refuse to make a sound until the person has interacted with the page, so a failure
// here is normal and silent: the bell still rings and the count still changes.
export function alarm() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext
    if (!Ctx) return
    const ctx = new Ctx()
    if (ctx.state === 'suspended') ctx.resume()
    const at = ctx.currentTime
    for (const [n, hz] of [[0, 880], [1, 1175]]) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = hz
      // Shaped rather than switched: a square-edged tone clicks on the way in and out.
      gain.gain.setValueAtTime(0.0001, at + n * 0.22)
      gain.gain.exponentialRampToValueAtTime(0.22, at + n * 0.22 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + n * 0.22 + 0.18)
      osc.connect(gain); gain.connect(ctx.destination)
      osc.start(at + n * 0.22); osc.stop(at + n * 0.22 + 0.2)
    }
    setTimeout(() => ctx.close().catch(() => {}), 1200)
  } catch { /* no sound available; the bell still rings */ }
}

// Full-width header: brand on the left; notifications, who is signed in, and sign-out on the right.
export default function TopBar({ user, admin }) {

  const [settings, setSettings] = useState(false)
  return (
    <header className="topbar">
      <Link to={admin ? '/admin' : '/'} className="brand">
        <span className="mark"><ShieldCheck /></span> TripProof Online
      </Link>
      {/* Outside the brand: the brand is held to the sidebar's width, and the tag would wrap it. */}
      {admin && <span className="tag">Admin</span>}
      <div className="spacer" />
      <Notifications />
      <button type="button" className="whoami" onClick={() => setSettings(true)} title="My settings">
        <span className="muted">Signed in as</span> <b>{user.name}</b> <ChevronDown size={14} />
      </button>
      <button onClick={signOut} aria-label="Sign out"><LogOut size={14} /> <span className="label">Sign out</span></button>
      {/* Portaled out of the header so the dialog doesn't inherit the bar's white-on-teal styling. */}
      {settings && createPortal(<MySettings user={user} onClose={() => setSettings(false)} />, document.body)}
    </header>
  )
}

// The signed-in person's own settings. Saving reloads so every timestamp on screen is redrawn in
// the new zone.
function MySettings({ user, onClose }) {
  const [tz, setTz] = useState(user.usertimezone)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const save = async () => {
    setBusy(true); setError(null)
    try { await api.put('/auth/me', { timezone: tz }); window.location.reload() } catch (e) { setError(e.message); setBusy(false) }
  }
  return (
    <Modal width={480} title="My settings" onClose={onClose}
      footer={<><button onClick={onClose}>Cancel</button><button className="primary" onClick={save} disabled={busy}>Save</button></>}>
      <div className="kv"><dt>Name</dt><dd>{user.name}</dd><dt>Email</dt><dd>{user.email}</dd></div>
      <label className="field">Time zone<TimeZoneSelect value={tz} onChange={(e) => setTz(e.target.value)} /></label>
      <div className="small muted">Dates and times are shown in this time zone.{!user.platformrole && ' Trip and credential dates always show as recorded, in your company’s local time.'}</div>
      {error && <div className="error">{error}</div>}
    </Modal>
  )
}

function Notifications() {
  const [data, setData] = useState({ unread: 0, items: [] })
  const [open, setOpen] = useState(false)
  // Something new has landed. The bell rings - visibly: two rings going out from it, the way a
  // struck bell is drawn. It fires on the count GOING UP, so a refresh that finds the same
  // notifications sitting there does not ring again.
  const [ringing, setRinging] = useState(false)
  const seen = useRef(null)
  const box = useRef()
  const navigate = useNavigate()

  const load = () => api.get('/notifications').then((got) => {
    setData(got)
    const was = seen.current
    seen.current = got.unread
    if (was !== null && got.unread > was) {
      // Only for the level that means somebody is waiting on an answer. An expiring credential
      // must not make a noise, or the noise stops meaning anything.
      if ((got.items || []).some((n) => !n.read && n.level === 'bad')) alarm()
      setRinging(false)
      // Off, then on in the next frame, so a second arrival restarts the animation rather than
      // landing mid-way through the first one and showing nothing.
      requestAnimationFrame(() => requestAnimationFrame(() => setRinging(true)))
    }
  }).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(load, POLL_MS)
    // The toast and the bell are two views of the same arrival, so they must not find out about it
    // at different times: whichever notices first tells the other. Without this the corner of the
    // screen announces a document and the bell catches up minutes later.
    const now = () => load()
    window.addEventListener('tripproof:arrived', now)
    return () => { clearInterval(t); window.removeEventListener('tripproof:arrived', now) }
  }, [])

  // Close on a click outside or Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const markRead = async (keys) => {
    if (!keys.length) return
    setData((d) => ({ unread: Math.max(0, d.unread - d.items.filter((n) => !n.read && keys.includes(n.key)).length),
      items: d.items.map((n) => (keys.includes(n.key) ? { ...n, read: true } : n)) }))
    await api.post('/notifications/read', { keys }).catch(() => {})
  }
  // These are computed from live data rather than stored, so clearing one can only mean marking it
  // read - and a notification that has been read has done its job and should stop taking up the
  // panel. It comes back if the thing happens again, which is the behaviour anybody wants: the
  // list is what is waiting on you, not a history of what once was.
  const showing = (data.items || []).filter((n) => !n.read)

  const openItem = (n) => {
    markRead([n.key])
    setOpen(false)
    if (n.link) navigate(n.link)
  }

  return (
    <div className="notify" ref={box}>
      <button className={`iconbtn bell${ringing ? ' ringing' : ''}`}
        onClick={() => setOpen((o) => !o)} aria-haspopup="true" aria-expanded={open}
        onAnimationEnd={() => setRinging(false)}
        aria-label={data.unread ? `Notifications, ${data.unread} unread` : 'Notifications'}>
        <Bell size={18} />
        <span className="ring" aria-hidden="true" />
        <span className="ring two" aria-hidden="true" />
        {data.unread > 0 && <span className="count">{data.unread > 99 ? '99+' : data.unread}</span>}
      </button>
      {open && (
        <div className="popover" role="menu">
          <div className="popover-head">
            <b>Notifications</b>
            {showing.length > 0 && (
              <button className="linkbtn"
                onClick={() => markRead(showing.map((n) => n.key))}>
                <CheckCheck size={14} /> Clear all
              </button>
            )}
          </div>
          {showing.length === 0 ? <div className="muted popover-empty">You’re all caught up.</div> : (
            <ul>
              {showing.map((n) => {
                const Icon = LEVEL_ICON[n.level] || Info
                return (
                  <li key={n.key} className={n.read ? 'read' : ''}>
                    <button onClick={() => openItem(n)} role="menuitem">
                      <span className={`lvl ${n.level}`}><Icon size={16} /></span>
                      <span className="txt">
                        <span className="t">{n.title}</span>
                        {n.detail && <span className="d">{n.detail}</span>}
                      </span>
                      {!n.read && <span className="dot" aria-label="unread" />}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
