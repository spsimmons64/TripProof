import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowRight, Check, Clock, LogOut, ClipboardCheck, ListChecks, MapPin, Navigation, Navigation2, Phone, RefreshCw,
  UserCheck } from 'lucide-react'
import { date, time } from '../lib/format.js'

// The driver's app.
//
// Built for one thumb, in a vehicle, in daylight. Everything here follows from that:
//
//   ONE BUTTON IS OBVIOUSLY THE NEXT ONE. A driver glancing at this between mirrors should not
//   have to read four options. The thing to press now is full width and said in words - "On the
//   way", "At the pickup" - never a state name out of a database.
//
//   THE PHONE IS OFTEN NOT ON THE NETWORK. Every action records the moment it HAPPENED on the
//   device and sends that with it, so a tap in dead ground is filed at the time of the tap and
//   not at the time the signal came back. A failed send says so and leaves the button pressable.
//
//   NOTHING HERE DECIDES ANYTHING. A driver reports what happened. Whether a passenger who did
//   not come out is a no-show is the broker's procedure and the office's judgement, so this app
//   raises it as an issue and never files the determination.

const TOKEN = 'tripproof.driver'
// localStorage, not sessionStorage: a driver who closes the app between trips must not be signed
// out. The token is a shift long and the server ends it either way.
const held = {
  get: () => { try { return localStorage.getItem(TOKEN) } catch { return null } },
  set: (v) => { try { v ? localStorage.setItem(TOKEN, v) : localStorage.removeItem(TOKEN) } catch { /* private window */ } },
}

async function call(path, body, method) {
  const r = await fetch(`/api/driver${path}`, {
    method: method || (body ? 'POST' : 'GET'),
    headers: { 'Content-Type': 'application/json',
               ...(held.get() ? { Authorization: `Bearer ${held.get()}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  const said = await r.json().catch(() => null)
  if (r.status === 401) {
    // The server knows WHY - signed in elsewhere, access closed, session expired - and a driver
    // told the right one of those does not walk to the office to ask.
    held.set(null)
    throw new Error(said?.detail || 'Signed out. Sign in again.')
  }
  if (!r.ok) throw new Error(said?.detail || 'That did not go through. Try again.')
  return said
}

// Where the phone is, asked for at the moment something happens rather than tracked all day: a
// position is useful because it is attached to an event, and a background trail costs battery a
// driver needs for the rest of the shift.
const where = () => new Promise((done) => {
  if (!navigator.geolocation) return done({})
  navigator.geolocation.getCurrentPosition(
    (p) => done({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
    () => done({}),
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 },
  )
})

const moment = async () => ({ at: new Date().toISOString().slice(0, 19), ...(await where()) })

// The driver's own clock, in their own words. Not the shared date helpers: those read a business
// date out of a stored string, and this is a moment that happened on this phone.
const said = (when) => when.toLocaleString(undefined, {
  month: '2-digit', day: '2-digit', year: 'numeric', hour: 'numeric', minute: '2-digit',
}).replace(',', '')

// Where the driver is, for as long as they are signed in --------------------------------------
//
// The office needs a position without a driver doing anything about it, so this runs on its own
// from the moment somebody signs in. Three things make it survive a real shift:
//
//   IT KEEPS WHAT IT CANNOT SEND. Fixes go into a queue in the phone's own storage and are sent in
//   batches. Out of signal the queue grows; back in signal it empties. Nothing is thrown away for
//   arriving late - every fix carries the moment it was TAKEN, which is what the trail is drawn
//   from.
//
//   IT DOES NOT REPORT A PARKED VAN ALL DAY. A fix is kept when the driver has moved more than
//   about 40 metres or a minute has passed. A vehicle standing outside a dialysis centre for three
//   hours produces a position every minute, not one every second.
//
//   IT SAYS WHEN IT CANNOT. Permission refused, or the phone has no fix, is shown on screen -
//   because a driver who thinks the office can see them, when it cannot, is the worst case.
//   IT COSTS LESS WHEN NOTHING IS HAPPENING. A driver between trips is answering one question -
//   where are you, roughly - so a fix every two minutes is enough, and the phone can sleep its
//   radio in between. On a trip the office is watching an arrival, so it reports on movement.
const QUEUE = 'tripproof.driver.fixes'
// Driving, then idle. The second number of each pair is what a parked van between trips costs.
const SEND_EVERY = { driving: 45000, idle: 120000 }   // how often the queue is emptied
const KEEP_EVERY = { driving: 60000, idle: 120000 }   // a fix at least this often, regardless
const KEEP_METRES = { driving: 40, idle: null }       // or this far - null means time alone

const queue = {
  read: () => { try { return JSON.parse(localStorage.getItem(QUEUE) || '[]') } catch { return [] } },
  write: (v) => { try { localStorage.setItem(QUEUE, JSON.stringify(v.slice(-500))) } catch { /* full */ } },
}

// Rough metres between two fixes. Good to a few per cent at these distances, which is far more
// than enough to answer "has this vehicle moved".
const apart = (a, b) => {
  const r = 6371000, p = Math.PI / 180
  const dLat = (b.latitude - a.latitude) * p
  const dLng = (b.longitude - a.longitude) * p
  const x = Math.sin(dLat / 2) ** 2
    + Math.cos(a.latitude * p) * Math.cos(b.latitude * p) * Math.sin(dLng / 2) ** 2
  return 2 * r * Math.asin(Math.sqrt(x))
}

function useReporting(on, driving) {
  const [state, setState] = useState('starting')   // starting | reporting | denied | nofix
  // When the office last actually HEARD from this phone - not when a fix was taken. A driver who
  // has been out of signal for twenty minutes is still taking positions; what they need to know
  // is that none of them have arrived.
  const [sentat, setSentAt] = useState(null)
  const last = useRef(null)
  // Read through a ref so changing pace does not tear down the watch and ask the phone for
  // permission all over again: the rate changes, the subscription does not.
  const pace = useRef(driving)
  pace.current = driving
  useEffect(() => {
    if (!on) return undefined
    if (!navigator.geolocation) { setState('denied'); return undefined }

    const keep = (p) => {
      const how = pace.current ? 'driving' : 'idle'
      const fix = { at: new Date(p.timestamp).toISOString().slice(0, 19),
                    latitude: p.coords.latitude, longitude: p.coords.longitude }
      const before = last.current
      const far = KEEP_METRES[how]
      const moved = far !== null && (!before || apart(before, fix) > far)
      // Measured on the wall clock, NOT on the position's own timestamp.
      //
      // A fix carries the moment the device says it was taken, and that moment can stand still:
      // a phone handing back a cached position returns the stamp it was originally taken at, so
      // "has two minutes passed" was asked of a number that never moved, answered no for ever,
      // and a parked van stopped reporting altogether. The stamp is still what we SEND - it is
      // when the fix happened - but it is not what we time ourselves by.
      const waited = !before || (Date.now() - before.seen) > KEEP_EVERY[how] - 2000
      if (!moved && !waited) return
      last.current = { ...fix, seen: Date.now() }
      queue.write([...queue.read(), fix])
      setState('reporting')
    }
    const watch = navigator.geolocation.watchPosition(
      keep,
      (e) => setState(e.code === e.PERMISSION_DENIED ? 'denied' : 'nofix'),
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 30000 },
    )

    // The heartbeat, and the reason this cannot be left to `watchPosition` alone: a watch fires
    // when the position CHANGES, so a phone sitting still in a yard fires nothing, queues
    // nothing, sends nothing - and the office sees a driver who last reported half an hour ago
    // and cannot tell that from one whose phone has died. A parked van is exactly the case where
    // somebody wants to know where it is parked.
    //
    // `maximumAge: 0` because a cached fix carries the timestamp it was taken at, which would
    // report an hour-old position as news.
    const beat = () => navigator.geolocation.getCurrentPosition(
      (p) => { keep(p); flush() },
      (e) => setState(e.code === e.PERMISSION_DENIED ? 'denied' : 'nofix'),
      { enableHighAccuracy: false, maximumAge: 0, timeout: 20000 },
    )
    let heart = setInterval(beat, KEEP_EVERY.idle)

    let sending = false
    const flush = async () => {
      const held = queue.read()
      if (sending || !held.length || !navigator.onLine) return
      sending = true
      try {
        await call('/positions', { fixes: held })
        // Only what was sent is dropped: anything recorded while the request was in flight stays.
        queue.write(queue.read().slice(held.length))
        setSentAt(new Date())
      } catch { /* keep them and try again */ } finally { sending = false }
    }
    // The slower of the two, re-armed when the pace changes - a trip starting does not have to
    // wait two minutes for its first report.
    // The first fix is taken and sent at once, not waited for. `watchPosition` may sit silent for
    // half a minute while the phone warms its radio, and the queue only empties on a timer - so a
    // driver who has just signed in would be invisible on the office map for up to two minutes
    // while standing in the yard. One single-shot read, straight up.
    navigator.geolocation.getCurrentPosition(
      (p) => {
        keep(p)
        flush()
      },
      (e) => setState(e.code === e.PERMISSION_DENIED ? 'denied' : 'nofix'),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )

    let timer = setInterval(flush, SEND_EVERY.idle)
    let running = 'idle'
    const repace = setInterval(() => {
      const how = pace.current ? 'driving' : 'idle'
      if (how === running) return
      running = how
      clearInterval(timer); clearInterval(heart)
      timer = setInterval(flush, SEND_EVERY[how])
      heart = setInterval(beat, KEEP_EVERY[how])
      beat()
    }, 5000)
    const wake = () => { if (document.visibilityState === 'visible') flush() }
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('online', flush)
    flush()
    return () => {
      navigator.geolocation.clearWatch(watch)
      clearInterval(timer)
      clearInterval(heart)
      clearInterval(repace)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('online', flush)
    }
  }, [on])
  return { state, sentat }
}

// The screen going dark stops a browser reporting anything. While a trip is actually running the
// app asks to keep it awake, which is the only thing a web app can do about it - and is why the
// phone belongs in a cradle on the dash.
function useAwake(on) {
  useEffect(() => {
    if (!on || !navigator.wakeLock) return undefined
    let held = null, dropped = false
    const take = async () => {
      try { held = await navigator.wakeLock.request('screen') } catch { /* refused or unsupported */ }
    }
    const again = () => { if (document.visibilityState === 'visible' && !dropped) take() }
    take()
    document.addEventListener('visibilitychange', again)
    return () => {
      dropped = true
      document.removeEventListener('visibilitychange', again)
      try { held?.release() } catch { /* already gone */ }
      }
  }, [on])
}

export default function DriverApp() {
  const [me, setMe] = useState(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!held.get()) { setReady(true); return }
    call('/me').then(setMe).catch(() => held.set(null)).finally(() => setReady(true))
  }, [])

  if (window.location.pathname.startsWith('/drive/password')) return <SetPassword onIn={setMe} />
  if (!ready) return <div className="dvapp"><div className="dvwait">One moment…</div></div>
  if (!me) return <SignIn onIn={setMe} />
  return <Work me={me} onOut={() => { held.set(null); setMe(null) }} />
}

function Shell({ children, title, right, menu }) {
  return (
    <div className="dvapp">
      <header className="dvhead">
        <span className="dvbrand">TripProof</span>
        <span className="dvtitle">{title}</span>
        {right}
      </header>
      <main className="dvbody">{children}</main>
      {/* At the bottom, where the thumb is. Two pages, both of which a driver needs every day. */}
      {menu}
    </div>
  )
}

function SignIn({ onIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const go = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const got = await call('/signin', { email: email.trim(), password })
      held.set(got.token)
      onIn(await call('/me'))
    } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <Shell title="Sign in">
      <form className="dvform" onSubmit={go}>
        {err && <div className="dverr">{err}</div>}
        <label className="dvfield">Email
          <input type="email" inputMode="email" autoComplete="username" autoCapitalize="none"
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="dvfield">Password
          <input type="password" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button className="dvgo" disabled={busy || !email || !password}>
          {busy ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
    </Shell>
  )
}

function SetPassword({ onIn }) {
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const short = password.length > 0 && password.length < 10
  const go = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const got = await call('/password', { token, password })
      held.set(got.token)
      window.history.replaceState({}, '', '/drive')
      onIn(await call('/me'))
    } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <Shell title="Set your password">
      <form className="dvform" onSubmit={go}>
        {err && <div className="dverr">{err}</div>}
        <label className="dvfield">New password
          <input type="password" autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {short && <div className="dvnote">Ten characters or more.</div>}
        <label className="dvfield">Type it again
          <input type="password" autoComplete="new-password"
            value={again} onChange={(e) => setAgain(e.target.value)} />
        </label>
        {again && again !== password && <div className="dvnote">Those two do not match.</div>}
        <button className="dvgo" disabled={busy || short || !password || password !== again}>
          {busy ? 'Saving…' : 'Save And Sign In'}
        </button>
      </form>
    </Shell>
  )
}

// The vehicle check. 49 CFR 396.11 puts this on the driver, and 396.13 says they must read the
// last one before driving - so the last report is shown first, and an uncorrected defect is said
// before anything is asked.
// `vehicle` opens it on one vehicle, and `onFiled` is told when a clean check has gone in - a trip
// that sent the driver here to do its pre-trip check takes them back to it.
function VehicleCheck({ me, reporting, vehicle = null, onFiled }) {
  const [list, setList] = useState(null)
  const [vehicleid, setVehicle] = useState(vehicle)
  const [seen, setSeen] = useState(null)
  const [kind, setKind] = useState('pretrip')
  const [defects, setDefects] = useState(null)       // null | false | true
  const [defectnote, setNote] = useState('')
  const [odometer, setOdo] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [done, setDone] = useState(null)

  useEffect(() => {
    call('/vehicles').then((got) => {
      setList(got)
      setVehicle((v) => v ?? got.items[0]?.recordid ?? null)
    }).catch((e) => setErr(e.message))
  }, [])
  useEffect(() => {
    if (!vehicleid) return
    setSeen(null); setDone(null)
    call(`/vehicles/${vehicleid}/lastcheck`).then(setSeen).catch(() => setSeen({}))
  }, [vehicleid])

  const file = async () => {
    setBusy(true); setErr(null)
    try {
      await call(`/vehicles/${vehicleid}/check`, {
        kind, defects: Boolean(defects), defectnote,
        odometer: odometer === '' ? null : Number(odometer),
      })
      setDone(defects ? 'defect' : 'clean')
      const clean = !defects
      setDefects(null); setNote(''); setOdo('')
      setSeen(await call(`/vehicles/${vehicleid}/lastcheck`))
      if (clean && kind === 'pretrip') onFiled?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (!list) return <div className="dvwait">One moment…</div>
  const already = (seen?.today || []).some((x) => x.kind === kind)

  return (
    <>
      <Reporting {...reporting} />
      {err && <div className="dverr">{err}</div>}

      <label className="dvfield">Vehicle
        <select value={vehicleid || ''} onChange={(e) => setVehicle(e.target.value)}>
          {list.items.map((v) => (
            <option key={v.recordid} value={v.recordid}>
              {[v.externalid, v.make, v.model].filter(Boolean).join(' · ')}{v.mine ? ' — yours today' : ''}
            </option>
          ))}
        </select>
      </label>

      {/* The 396.13 review: what the last person wrote, before this one writes anything. */}
      {seen?.outstanding && (
        <div className="dverr">
          <b>This vehicle has a defect that has not been put right.</b><br />
          {seen.outstanding.defectnote}<br />
          Reported {date(seen.outstanding.reportedon)}
          {seen.outstanding.drivername ? ` by ${seen.outstanding.drivername}` : ''}. It must not be
          driven until the office certifies the repair.
        </div>
      )}
      {seen && !seen.outstanding && seen.last && (
        <div className="dvlast">
          Last checked {date(seen.last.reportedon)}
          {seen.last.drivername ? ` by ${seen.last.drivername}` : ''} ·{' '}
          {seen.last.defects ? 'defect found, since put right' : 'no defects'}
        </div>
      )}
      {seen && !seen.last && <div className="dvlast">No inspection has ever been filed on this vehicle.</div>}

      <div className="dvpick">
        {Object.entries(list.kinds).map(([k, label]) => (
          <button key={k} type="button" className={`dvchip${kind === k ? ' on' : ''}`}
            onClick={() => { setKind(k); setDone(null) }}>{label}</button>
        ))}
      </div>
      {already && <div className="dvlast">You already filed this one today. Another will be added.</div>}

      <label className="dvfield">Odometer, if you can read it
        <input type="number" inputMode="numeric" value={odometer}
          onChange={(e) => setOdo(e.target.value)} />
      </label>

      <button type="button" className={`dvgo${defects === false ? '' : ' quiet'}`} disabled={busy}
        onClick={() => { setDefects(false); setNote('') }}>
        <Check size={20} /> No Defects Found
      </button>
      <button type="button" className={`dvtrouble${defects === true ? ' on' : ''}`} disabled={busy}
        onClick={() => setDefects(true)}>
        <AlertTriangle size={18} /> Something Is Wrong With It
      </button>
      {defects === true && (
        <label className="dvfield">What is wrong *
          <input value={defectnote} onChange={(e) => setNote(e.target.value)} autoFocus />
        </label>
      )}

      {defects !== null && (
        <button type="button" className="dvgo" disabled={busy || (defects && !defectnote.trim())}
          onClick={file}>
          {busy ? 'Filing…' : `File The ${list.kinds[kind]} Check`}
        </button>
      )}
      {done === 'clean' && <div className="dvdone"><Check size={18} /> Filed. Nothing wrong with it.</div>}
      {done === 'defect' && (
        <div className="dverr">Filed. The office has it. This vehicle must not be driven until
          they certify the repair.</div>
      )}
    </>
  )
}

function Work({ me, onOut }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(null)      // the legid being worked
  const [where, setWhere] = useState('trips') // which of the app's pages
  const [checkFor, setCheckFor] = useState(null) // the trip that sent the driver to inspect
  const go = (to) => { setWhere(to); setOpen(null) }
  const load = useCallback(async () => {
    try { setData(await call('/trips')); setErr(null) } catch (x) { setErr(x.message) }
  }, [])
  useEffect(() => { load() }, [load])
  // The list is re-read on a timer as well as after every action: the office can reassign a trip
  // while a driver is looking at it, and a driver acting on a stale list is a trip done twice.
  useEffect(() => {
    const t = setInterval(load, 60000)
    const wake = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', wake)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', wake) }
  }, [load])

  const items = data?.items || []
  // Reporting runs from sign-in to sign-out, not from trip to trip: the office asks "where is
  // everybody" long before a driver has pressed anything.
  const driving = items.some((x) => ['enroute', 'arrived', 'onboard'].includes(x.executionstate))
  const reporting = useReporting(true, driving)
  // The screen is kept awake only while a trip is actually under way. All day would be a flat
  // battery by two o'clock.
  useAwake(driving)
  // The pre-trip check a trip asked for, on that trip's vehicle, and back to the trip once filed.
  if (checkFor) {
    const back = () => { setCheckFor(null); setOpen(checkFor.legid) }
    return (
      <Shell title="Pre-Trip Check"
        right={<button className="dvicon" onClick={back} aria-label="Back">✕</button>}>
        <VehicleCheck me={me} reporting={reporting} vehicle={checkFor.vehicleid}
          onFiled={async () => { await load(); back() }} />
      </Shell>
    )
  }
  const leg = items.find((x) => x.legid === open)
  if (leg) {
    return <Trip me={me} leg={leg} reporting={reporting}
      onBack={() => setOpen(null)} onDone={load}
      onCheck={() => { setOpen(null); setCheckFor({ legid: leg.legid, vehicleid: leg.vehicleid }) }} />
  }

  const menu = (
    <nav className="dvmenu">
      <button type="button" className={where === 'trips' ? 'on' : ''} onClick={() => go('trips')}>
        <ListChecks size={20} /> My Trips
      </button>
      <button type="button" className={where === 'check' ? 'on' : ''} onClick={() => go('check')}>
        <ClipboardCheck size={20} /> Vehicle Check
      </button>
    </nav>
  )

  if (where === 'check') {
    return (
      <Shell title="Vehicle Check" menu={menu}
        right={<button className="dvicon" onClick={onOut} aria-label="Sign out"><LogOut size={20} /></button>}>
        <VehicleCheck me={me} reporting={reporting} />
      </Shell>
    )
  }

  return (
    <Shell title={me.name} menu={menu}
      right={<button className="dvicon" onClick={onOut} aria-label="Sign out"><LogOut size={20} /></button>}>
      {err && <div className="dverr">{err}</div>}
      <Reporting {...reporting} />
      <div className="dvlisthead">
        <span>{items.length ? `${items.length} trip${items.length === 1 ? '' : 's'}` : 'Nothing assigned'}</span>
        <button className="dvicon" onClick={load} aria-label="Refresh"><RefreshCw size={18} /></button>
      </div>
      <div className="dvlist">
      {items.map((t) => (
        <button key={t.legid} className={`dvrow${t.executionstate === 'completed' ? ' done' : ''}`}
          onClick={() => setOpen(t.legid)}>
          <span className="dvrowtext">
            <span className="dvrowtop">
              <span className="dvtime">{t.pickupat ? time(t.pickupat) : 'Will-call'}</span>
              <span className="dvwho">{t.passenger}</span>
            </span>
            <span className="dvaddr">{t.pickupplace}</span>
          </span>
          <Standing leg={t} />
        </button>
      ))}
      </div>
      {!items.length && !err && (
        <p className="dvempty">Nothing is assigned to you right now.</p>
      )}
    </Shell>
  )
}

// Where this leg has got to, as one mark. A row a driver scans down between jobs should answer
// "which of these have I done" without being read - so the state is a shape and a colour, with
// the words kept for the trip itself. Titled, so it is not colour alone.
const STANDING = {
  scheduled: [Clock, 'Not started', 'wait'],
  enroute: [Navigation2, 'On the way', 'go'],
  arrived: [MapPin, 'At the pickup', 'go'],
  onboard: [UserCheck, 'Passenger aboard', 'go'],
  completed: [Check, 'Completed', 'done'],
}

function Standing({ leg }) {
  if (leg.waitingid) {
    return <span className="dvmark waiting" title="Waiting"><Clock size={20} /></span>
  }
  const [Icon, says, tone] = STANDING[leg.executionstate] || STANDING.scheduled
  const moving = ['enroute', 'arrived', 'onboard'].includes(leg.executionstate)
  return (
    <span className={`dvmark ${tone}${moving ? ' moving' : ''}`} title={says} aria-label={says}>
      <Icon size={20} />
    </span>
  )
}

// Whether the office can see this driver. Said plainly, because somebody who believes they are
// being tracked when they are not is worse off than somebody who knows they are not.
// A clock, not a claim. "The office can see your location" is a promise the app cannot keep in a
// dead spot; the time of the last position that actually arrived is a fact the driver can act on.
function Reporting({ state, sentat }) {
  if (state === 'reporting') {
    return (
      <div className="dvgps on">
        <Navigation size={14} />
        Location last reported at: {sentat ? said(sentat) : 'sending…'}
      </div>
    )
  }
  if (state === 'denied') {
    return (
      <div className="dvgps off">
        <Navigation size={14} /> Location is switched off, so the office cannot see where you are.
        Turn it on for this site in your phone&rsquo;s settings.
      </div>
    )
  }
  if (state === 'nofix') {
    return <div className="dvgps wait"><Navigation size={14} /> Looking for a signal…</div>
  }
  return <div className="dvgps wait"><Navigation size={14} /> Starting location…</div>
}

// Navigation is handed to the phone, not rebuilt here.
//
// The driver already has an app with voice, traffic and rerouting, and - the part that matters -
// one that keeps guiding when the screen is off and the browser is in the background, which a web
// app cannot do. Building a worse version of that inside this one would be the wrong kind of
// ambition. What this app knows and the phone does not is WHICH address, and when it changes from
// the pickup to the destination; that is the whole of its job here.
//
// Coordinates are used where the address was geocoded when the trip was booked - "6600 MADISON
// ST" matches several places in Florida and a driver should not be the one discovering that.
function navigateTo(place, lat, lng) {
  const to = (lat !== null && lat !== undefined && lng !== null && lng !== undefined)
    ? `${lat},${lng}` : place
  const where = encodeURIComponent(to)
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  // Apple Maps is on every iPhone; Google's navigation intent starts turn-by-turn directly on
  // Android. The https form is the fallback that works anywhere, including a tablet in a browser.
  const url = ios ? `maps://?daddr=${where}&dirflg=d`
    : /Android/.test(navigator.userAgent) ? `google.navigation:q=${where}`
      : `https://www.google.com/maps/dir/?api=1&destination=${where}&travelmode=driving`
  const w = window.open(url, '_blank')
  // A custom scheme that nothing handles opens nothing at all and leaves the driver pressing a
  // dead button, so the universal link is tried next.
  if (!w && !url.startsWith('https')) {
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${where}&travelmode=driving`,
                '_blank')
  }
}

function Trip({ me, leg, reporting, onBack, onDone, onCheck }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [asking, setAsking] = useState(null)    // 'issue' | 'wait'
  const onboard = leg.executionstate === 'onboard'
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); await onDone() } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  const step = (state) => act(async () =>
    call(`/legs/${leg.legid}/state`, { ...(await moment()), state }))

  return (
    <Shell title={leg.passenger}
      right={<button className="dvicon" onClick={onBack} aria-label="Back">✕</button>}>
      {err && <div className="dverr">{err}</div>}
      <Reporting {...reporting} />

      {/* Where they are going NEXT, which is the passenger until the passenger is aboard and
          the destination afterwards. One button, and it always means the right place.
          Nothing is offered while the clock is running: the wait is ended first, deliberately. */}
      {leg.executionstate !== 'completed' && !leg.waitingid && (
        <button className="dvnav" type="button" onClick={() => (onboard
          ? navigateTo(leg.dropoffplace, leg.dropofflat, leg.dropofflng)
          : navigateTo(leg.pickupplace, leg.pickuplat, leg.pickuplng))}>
          <Navigation2 size={20} /> Navigate To The {onboard ? 'Destination' : 'Pickup'}
        </button>
      )}

      <div className="dvtrip">
        <div className="dvfacts">
          <div className="dvrow"><span>Pickup</span><b>{leg.pickupat ? time(leg.pickupat) : 'Will-call'}</b></div>
          {/* The unit number and what it looks like. A driver sent to 00098 with four vans in
              front of them needs both. */}
          {leg.vehiclename && (
            <div className="dvrow"><span>Vehicle</span>
              <b>{[leg.vehiclename, leg.vehicledescr].filter(Boolean).join(' · ')}</b></div>
          )}
        </div>
        <div className="dvplaces">
          <div className="dvplace"><MapPin size={16} /><div><b>From</b>{leg.pickupplace}</div></div>
          <div className="dvplace"><MapPin size={16} /><div><b>To</b>{leg.dropoffplace}</div></div>
        </div>
        {leg.note && <div className="dvnote">{leg.note}</div>}
      </div>

      {/* Outside the card, with the other things a driver presses. Calling the passenger is an
          action, not a fact about the trip. */}
      {leg.passengerphone && (
        <a className="dvcall" href={`tel:${leg.passengerphone}`}>
          <Phone size={18} /> Call {leg.passenger}
        </a>
      )}

      {/* Waiting is offered only where the server will accept it, and the server is the one that
          says so. A driver who has not set off has nothing to wait for; one who is driving has a
          problem, not a wait - and in both cases the app says which rather than hiding a button
          and leaving somebody hunting for it. */}
      {leg.waitingid ? (
        <button className="dvgo waiting" disabled={busy}
          onClick={() => act(async () => call(`/legs/${leg.legid}/wait/end`, await moment()))}>
          <Clock size={20} /> Waiting since {time(leg.waitingsince)} · Done Waiting
        </button>
      ) : leg.canwait ? (
        <button className="dvsecond" disabled={busy} onClick={() => setAsking('wait')}>
          <Clock size={18} /> I Am Waiting
        </button>
      ) : leg.whynotwait ? (
        <div className="dvwhynot"><Clock size={16} /> {leg.whynotwait}</div>
      ) : null}

      {/* What has to happen before this trip can start: the day's pre-trip check of its vehicle,
          or a defect the office has to certify. Decided by the server, as every button here is. */}
      {leg.checkfirst?.kind === 'pretrip' && (
        <button className="dvgo" type="button" onClick={onCheck}>
          <ClipboardCheck size={20} /> Do The Pre-Trip Check Of {leg.checkfirst.vehiclename}
        </button>
      )}
      {leg.checkfirst?.kind === 'defect' && <div className="dverr">{leg.checkfirst.why}</div>}

      {leg.nextsaid && (
        <button className={`dvgo${leg.checkfirst ? ' quiet' : ''}`} disabled={busy}
          onClick={() => step(leg.next[0])}>
          {busy ? 'Sending…' : leg.nextsaid}
        </button>
      )}
      {leg.executionstate === 'completed' && (
        <div className="dvdone"><Check size={18} /> This trip is finished.</div>
      )}

      {/* A finished trip offers nothing. There is nothing left to wait for and nothing left to
          go wrong with it - anything after the drop-off is the office's to sort out, and a
          screen still offering to start a clock on it invites exactly that. */}
      {/* One problem at a time. A driver who has reported something and sees no sign of it will
          press the button again - which is the sensible thing to do when a screen gives no sign
          of having heard you - and the office then gets the same flat tyre twice. So the button
          is replaced by what was reported and whether anybody has picked it up, which is what
          the driver wanted to know by pressing it a second time. */}
      {leg.executionstate !== 'completed' && (leg.issueid ? (
        <div className="dvwhynot">
          <AlertTriangle size={16} /> {me.issues[leg.issuekind] || 'A problem'} told to the
          office at {time(leg.issueraisedon)}
          {leg.issueseen ? ` · seen at ${time(leg.issueseen)}` : ' · not seen yet'}
        </div>
      ) : (
        <button className="dvtrouble" disabled={busy} onClick={() => setAsking('issue')}>
          <AlertTriangle size={18} /> Tell The Office A Problem
        </button>
      ))}

      {asking === 'issue' && (
        <Picker title="What is wrong?" options={me.issues}
          onClose={() => setAsking(null)}
          onPick={(kind, note) => act(async () => {
            await call(`/legs/${leg.legid}/issue`, { ...(await moment()), kind, note })
            setAsking(null)
          })} />
      )}
      {asking === 'wait' && (
        <Picker title="What are you waiting on?" options={me.waitreasons}
          onClose={() => setAsking(null)}
          onPick={(reason, note) => act(async () => {
            await call(`/legs/${leg.legid}/wait`, { ...(await moment()), reason, note })
            setAsking(null)
          })} />
      )}
    </Shell>
  )
}

// One question, big targets, and a place to say more. The same sheet for both because they are
// the same act: telling the office something, from a list the server decides.
function Picker({ title, options, onPick, onClose }) {
  const [note, setNote] = useState('')
  return (
    <div className="dvsheet" role="dialog" aria-label={title}>
      <div className="dvsheetbody">
        <h2>{title}</h2>
        {Object.entries(options).map(([k, label]) => (
          <button key={k} className="dvoption" onClick={() => onPick(k, note.trim() || null)}>
            {label}
          </button>
        ))}
        <label className="dvfield">Anything to add
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="dvsecond" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}
