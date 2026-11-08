import { useCallback, useEffect, useState } from 'react'
import { CalendarClock, ChevronLeft, ChevronRight, Loader2, LogOut, Plus, ShieldCheck } from 'lucide-react'
import { Modal } from '../admin/common.jsx'
import DataGrid from '../components/DataGrid.jsx'
import { date } from '../lib/format.js'

// The facility portal: a dialysis centre, clinic or hospital's own window on the trips to and from
// its door. A different application served from the same place, like the driver's app: its own
// sign-in, its own session, nothing of the office's. Kept in sessionStorage, as the office's is - a
// front desk PC is a shared PC.
const TOKEN = 'tripproof.facility'
const held = {
  get: () => { try { return sessionStorage.getItem(TOKEN) } catch { return null } },
  set: (v) => { try { v ? sessionStorage.setItem(TOKEN, v) : sessionStorage.removeItem(TOKEN) } catch { /* private window */ } },
}

async function call(path, body, method) {
  const r = await fetch(`/api/facility${path}`, {
    method: method || (body ? 'POST' : 'GET'),
    headers: { 'Content-Type': 'application/json', ...(held.get() ? { Authorization: `Bearer ${held.get()}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  const said = await r.json().catch(() => null)
  if (r.status === 401) { held.set(null); throw Object.assign(new Error(said?.detail || 'Signed out. Sign in again.'), { out: true }) }
  if (!r.ok) throw new Error(typeof said?.detail === 'string' ? said.detail : 'That did not go through. Try again.')
  return said
}

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const shift = (day, n) => { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + n); return ymd(d) }

export default function FacilityApp() {
  const [me, setMe] = useState(null)
  const [ready, setReady] = useState(false)
  const load = useCallback(() => call('/me').then(setMe).catch(() => setMe(null)).finally(() => setReady(true)), [])
  useEffect(() => { if (held.get()) load(); else setReady(true) }, [load])
  if (window.location.pathname.startsWith('/facility/password')) return <SetPassword onIn={(t) => { held.set(t); window.history.replaceState(null, '', '/facility'); load() }} />
  if (!ready) return null
  if (!me) return <SignIn onIn={(t) => { held.set(t); load() }} />
  // A new login, so everything under it starts again for that company: `key` throws away the
  // schedule and any half-filled request belonging to the company being left.
  return <Portal key={me.id} me={me}
    onSwitch={async (id) => { held.set((await call('/switch', { id })).token); load() }}
    onOut={async () => { await call('/signout', {}).catch(() => {}); held.set(null); setMe(null) }} />
}

function SignIn({ onIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const go = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { onIn((await call('/signin', { email: email.trim(), password })).token) } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <div className="loginpage">
      <form className="card login stack" onSubmit={go}>
        <div className="brand"><span className="mark"><ShieldCheck /></span> TripProof</div>
        <div className="muted">Facility trip requests</div>
        <label className="field">Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value.toLowerCase())} required /></label>
        <label className="field">Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {err && <div className="error">{err}</div>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign In'}</button>
      </form>
    </div>
  )
}

function SetPassword({ onIn }) {
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const go = async (e) => {
    e.preventDefault()
    if (password !== again) { setErr('The two passwords are not the same.'); return }
    setBusy(true); setErr(null)
    try { onIn((await call('/password', { token, password })).token) } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <div className="loginpage">
      <form className="card login stack" onSubmit={go}>
        <div className="brand"><span className="mark"><ShieldCheck /></span> TripProof</div>
        <div className="muted">Choose your password</div>
        <label className="field">Password<input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <label className="field">Password Again<input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required /></label>
        {err && <div className="error">{err}</div>}
        <button className="primary" disabled={busy || password.length < 10}>{busy ? 'Saving…' : 'Save Password'}</button>
      </form>
    </div>
  )
}

function Portal({ me, onOut, onSwitch }) {
  const [page, setPage] = useState('schedule')
  const [day, setDay] = useState(() => ymd(new Date()))
  const [sent, setSent] = useState(null)
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand"><span className="mark"><ShieldCheck /></span> TripProof Online</span>
        <div className="spacer" />
        {/* The same person's logins at other transportation companies. One company at a time:
            switching opens that company's schedule and nothing else. */}
        {me.providers?.length > 1 && (
          <label className="providerpick">Transportation Provider
            <select value={me.id} onChange={(e) => onSwitch(e.target.value)}>
              {me.providers.map((x) => <option key={x.id} value={x.id}>{x.company}</option>)}
            </select>
          </label>
        )}
        <span className="whoami"><span className="muted">Signed in as</span> <b>{me.name}</b> · {me.place}</span>
        <button onClick={onOut} aria-label="Sign out"><LogOut size={14} /> <span className="label">Sign out</span></button>
      </header>
      <div className="shell">
        <nav className="side">
          <div>
            <a href="#schedule" className={page === 'schedule' ? 'active' : undefined}
              onClick={(e) => { e.preventDefault(); setPage('schedule') }}><CalendarClock size={16} /> Schedule</a>
            <a href="#request" className={page === 'request' ? 'active' : undefined}
              onClick={(e) => { e.preventDefault(); setSent(null); setPage('request') }}><Plus size={16} /> Request A Trip</a>
          </div>
        </nav>
        <main>
          {page === 'schedule'
            ? <Schedule me={me} day={day} setDay={setDay} sent={sent} onRequest={() => { setSent(null); setPage('request') }} />
            : <RequestTrip me={me} day={day} onBack={() => setPage('schedule')}
                onSent={(got, on) => { setSent(got); setDay(on); setPage('schedule') }} />}
        </main>
      </div>
    </div>
  )
}

const COLUMNS = [
  { id: 'pickup', label: 'Pickup', width: 90, sortable: false },
  { id: 'passenger', label: 'Passenger', width: 170, sortable: false },
  { id: 'direction', label: 'Direction', width: 110, sortable: false },
  { id: 'service', label: 'Service', width: 110, sortable: false },
  { id: 'billedto', label: 'Billed To', width: 110, sortable: false },
  { id: 'status', label: 'Status', width: 130, sortable: false },
  { id: 'progress', label: 'Progress', sortable: false },
  { id: 'act', label: '', width: 250, sortable: false },
]
const TONE = { Completed: 'st-active', Declined: 'st-expired', Canceled: 'st-expired', 'No-Show': 'st-expired' }

function Schedule({ me, day, setDay, sent, onRequest }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [asking, setAsking] = useState(null)     // { kind: ready | cancel | withdraw, row, charge }
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => call(`/schedule?day=${day}`).then((d) => { setData(d); setErr(null) }).catch((x) => setErr(x.message)), [day])
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [load])
  const ask = async (kind, r) => {
    setErr(null)
    if (kind !== 'cancel') { setAsking({ kind, row: r }); return }
    try { setAsking({ kind, row: r, charge: (await call(`/trips/${r.tripid}/cancel`)).charge }) } catch (x) { setErr(x.message) }
  }
  const yes = async () => {
    const { kind, row: r, charge } = asking
    setBusy(true)
    try {
      if (kind === 'ready') await call(`/legs/${r.id}/ready`, {})
      else if (kind === 'withdraw') await call(`/requests/${r.id}/withdraw`, {})
      else await call(`/trips/${r.tripid}/cancel`, { charge })
      setAsking(null); load()
    } catch (x) { setErr(x.message); setAsking(null) } finally { setBusy(false) }
  }
  const question = asking && (asking.kind === 'ready' ? `Is ${asking.row.passenger} ready to be picked up now?`
    : asking.kind === 'withdraw' ? `Cancel the request for ${asking.row.passenger}?`
    : asking.charge ? `Cancel ${asking.row.passenger}'s trip, with the $${asking.charge.toFixed(2)} late cancel charge?`
    : `Cancel ${asking.row.passenger}'s trip?`)
  return (
    <div className="fill">
      <div className="pagehead daypagehead">
        <h1>Schedule</h1>
        <div className="segs daypick">
          <button type="button" className="chip" aria-label="The day before" onClick={() => setDay(shift(day, -1))}><ChevronLeft size={16} /></button>
          <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
          <button type="button" className="chip" aria-label="The day after" onClick={() => setDay(shift(day, 1))}><ChevronRight size={16} /></button>
        </div>
        <div className="row pushright">
          <button type="button" className="primary" onClick={onRequest}><Plus size={14} /> Request A Trip</button>
        </div>
      </div>
      {sent && <div className="notice good">Request sent for {sent.passenger}, pickup {sent.pickup} on {date(sent.tripdate)}. Dispatch will accept or decline it.</div>}
      {err && <div className="notice bad">{err}</div>}
      <DataGrid className="facgrid" columns={COLUMNS} rows={data?.items} rowKey={(r) => r.id} loading={!data && !err}
        empty={`No trips to or from ${me.place} on ${date(day)}.`}
        cells={(r) => [
          <b>{r.pickup}</b>, r.passenger, r.direction, r.service, r.billedto,
          <span className={TONE[r.status]}>{r.status}</span>, r.progress || '',
          <span style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            {r.canready && <button type="button" className="primary" onClick={() => ask('ready', r)}>Ready For Pickup</button>}
            {r.cancancel && <button type="button" onClick={() => ask(r.kind === 'request' ? 'withdraw' : 'cancel', r)}>Cancel</button>}
          </span>,
        ]} />
      {asking && (
        <Modal title={asking.kind === 'ready' ? 'Ready For Pickup' : asking.kind === 'withdraw' ? 'Cancel Request' : 'Cancel Trip'}
          onClose={() => setAsking(null)} width={520}
          footer={<>
            <button type="button" className="primary" disabled={busy} onClick={yes}>{busy ? <Loader2 size={15} className="spin" /> : 'Yes'}</button>
            <button type="button" onClick={() => setAsking(null)}>No</button>
          </>}>
          <div className="stack"><div className="askorder"><span className="askmark">?</span><p>{question}</p></div></div>
        </Modal>
      )}
    </div>
  )
}

function Choice({ value, options, onChange }) {
  return (
    <div className="segs">
      {options.map(([v, label]) => (
        <button key={v} type="button" className={`chip${value === v ? ' on' : ''}`} aria-pressed={value === v} onClick={() => onChange(v)}>{label}</button>
      ))}
    </div>
  )
}

function RequestTrip({ me, day, onBack, onSent }) {
  const today = ymd(new Date())
  const [v, setV] = useState({ passenger: '', phone: '', servicelevel: Object.keys(me.services)[0], direction: 'to', address: '',
    tripdate: day < today ? today : day, time: '', returnmode: 'will', returntime: '', billto: me.contract ? 'contract' : 'private', note: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })
  const upper = (k) => (e) => setV({ ...v, [k]: e.target.value.toUpperCase() })
  const ok = v.passenger.trim() && v.phone.trim() && v.address.trim() && v.tripdate && v.time
    && (v.direction === 'from' || v.returnmode !== 'time' || v.returntime)
  const send = async () => {
    setBusy(true); setErr(null)
    try {
      const got = await call('/requests', { ...v, returnmode: v.direction === 'to' ? v.returnmode : 'none' })
      onSent({ ...got, passenger: v.passenger.trim(), tripdate: v.tripdate }, v.tripdate)
    } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <div className="fill">
      <div className="pagehead"><h1>Request A Trip</h1></div>
      <div className="card qualcard">
        <div className="infotabs"><h3>{me.place}</h3></div>
        <div className="panelbody stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="profileform">
            <label className="field span-3">Passenger *<input className="upper" value={v.passenger} onChange={upper('passenger')} /></label>
            <label className="field span-2">Phone *<input type="tel" value={v.phone} onChange={set('phone')} /></label>
            <label className="field span-1">Service *
              <select value={v.servicelevel} onChange={set('servicelevel')}>
                {Object.entries(me.services).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </label>
            <div className="field span-6">Trip
              <Choice value={v.direction} onChange={(d) => setV({ ...v, direction: d })}
                options={[['to', `To ${me.place}`], ['from', `From ${me.place}`]]} />
            </div>
            <label className="field span-6">{v.direction === 'to' ? 'Pickup Address *' : 'Drop-Off Address *'}
              <input className="upper" value={v.address} onChange={upper('address')} placeholder="STREET, CITY, ST ZIP" />
            </label>
            <label className="field span-2">Date *<input type="date" min={today} value={v.tripdate} onChange={set('tripdate')} /></label>
            <label className="field span-2">{v.direction === 'to' ? 'Appointment *' : 'Pickup *'}<input type="time" value={v.time} onChange={set('time')} /></label>
            {v.direction === 'to' && (<>
              <div className="field span-6">Return
                <Choice value={v.returnmode} onChange={(m) => setV({ ...v, returnmode: m })}
                  options={[['time', 'At A Set Time'], ['will', 'Will-Call'], ['none', 'No Return']]} />
              </div>
              {v.returnmode === 'time' && (
                <label className="field span-2">Return Pickup *<input type="time" value={v.returntime} onChange={set('returntime')} /></label>
              )}
            </>)}
            <div className="field span-6">Billed To
              <Choice value={v.billto} onChange={(b) => setV({ ...v, billto: b })}
                options={[...(me.contract ? [['contract', `${me.place} (Contract)`]] : []), ['private', 'Passenger (Private Pay)']]} />
            </div>
            <label className="field span-6">Note<textarea className="upper" rows={3} value={v.note} onChange={upper('note')} /></label>
          </div>
          <div className="row">
            <button type="button" onClick={onBack}>Back To Schedule</button>
            <div className="pushright">
              <button type="button" className="primary" disabled={busy || !ok} onClick={send}>
                {busy ? <Loader2 size={15} className="spin" /> : 'Send Request'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
