import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, CalendarRange, ChevronDown, ChevronLeft, ChevronRight, Loader2, Plus, Sparkles, UserPlus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time, tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import BookTrip from '../components/BookTrip.jsx'
import IssueDialog from '../components/IssueDialog.jsx'
import OutDialog from '../components/OutDialog.jsx'
import AssignDialog from '../components/AssignDialog.jsx'
import EditTrip from '../components/EditTrip.jsx'

// The day's work, laid out the way the day is read. On the left, every leg nobody is on yet; on
// the right, one column per driver on shift, the day running down the side in quarter hours, with
// the trips each one has where they fall. A leg is put on a driver by dragging it to their column
// - in the vehicle their shift gives them, through the same gate as the Assign dialog - or the
// whole list at once by Auto Assign. Once it has a driver it moves over to the calendar.
//
// A leg, not a trip, because a leg is what a driver is given: out to a clinic and back is two
// pieces of work, often for two drivers.

const SLOT = 28                      // pixels per quarter hour, as on the Shifts page
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const shift = (day, n) => { const [y, m, d] = day.split('-').map(Number); return ymd(new Date(y, m - 1, d + n)) }
const minutes = (hhmm) => { const [h, m] = String(hhmm).slice(0, 5).split(':').map(Number); return h * 60 + m }
const clock = (mins) => {
  const m = ((mins % 1440) + 1440) % 1440
  const h = Math.floor(m / 60)
  return `${h % 12 || 12}:${String(m % 60).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}
// Under way: set off, at the pickup, or with the passenger aboard.
const moving = (l) => ['enroute', 'arrived', 'onboard'].includes(l.executionstate) && !l.outcomestate
const at = (iso) => { const d = new Date(iso); return d.getHours() * 60 + d.getMinutes() }
const ends = (s) => { const a = minutes(s.startsat); const b = minutes(s.endsat); return b > a ? b : b + 1440 }

// The database's word for where a leg has got to, in the words an office uses out loud.
const SAID = {
  scheduled: 'Scheduled', enroute: 'En route', arrived: 'At pickup',
  onboard: 'Passenger aboard', completed: 'Completed',
}
const OUTCOME = { cancelled: 'Canceled', noshow: 'No-show', aborted: 'Aborted', disputed: 'Disputed' }

// A missed pickup is a question, not an answer. "Missed" means only that the hour went by and
// nobody pressed anything, so the board asks rather than guesses.
const WHATNOW = { missed: 'Missed', late: 'Running late' }
const ATTENTION = { nodriver: 'No Driver', reassign: 'Needs Reassigning' }

// The same problems the driver's app offers, in a word. The sentence belongs in the dialog.
const SHORT = {
  noshow: 'No-show', refused: 'Ride refused', address: 'Bad address', vehicle: 'Vehicle problem',
  medical: 'Medical', traffic: 'Held up', equipment: 'Equipment', other: 'A problem',
}

// Missed red, late or needing attention the warning colour, under way blue, finished green - the
// same colours the list used, so they are seen from across the room.
const tone = (l) => (l.unseen ? (l.executionstate === 'onboard' ? 'rowbad' : 'rowwarn')
  : l.outcomestate === 'disputed' ? 'rowwarn'
  : l.issueid && l.executionstate !== 'completed' ? 'rowbad'
  : l.outcomestate ? null
  : l.late === 'missed' ? 'rowbad' : l.late || l.attention ? 'rowwarn'
  : l.executionstate === 'completed' ? 'rowgood'
  : ['enroute', 'arrived', 'onboard'].includes(l.executionstate) ? 'rowmoving' : null)

export default function Dispatch() {
  // Coming back from a trip's page: the day it was on, with its dialog open again.
  const returned = useLocation().state
  const [day, setDay] = useState(() => returned?.day || ymd(new Date()))
  const [data, error, reload] = useLoad(async () => {
    const [board, roster, attention] = await Promise.all([
      api.get(`/dispatch/board?day=${day}&state=all&pagesize=200&sort=pickupat&dir=asc`),
      api.get(`/shifts?day=${day}`),
      // Whatever will not settle itself, from any day - the board above is one day only.
      api.get('/dispatch/board?state=attention&pagesize=200&sort=pickupat&dir=asc'),
    ])
    return { ...board, roster, attention: attention.items }
  }, [day])
  const [assigning, setAssigning] = useState(null)
  const [returning, setReturning] = useState(null)
  const [confirming, setConfirming] = useState(null)   // a returned trip the broker has confirmed
  const [cancelling, setCancelling] = useState(null)
  const [closing, setClosing] = useState(null)
  const [issue, setIssue] = useState(null)
  const [out, setOut] = useState(false)
  const [booking, setBooking] = useState(false)
  const [editing, setEditing] = useState(null)
  const [called, setCalled] = useState(null)       // the will-call leg whose passenger has rung
  const [looking, setLooking] = useState(returned?.open || null)     // the leg opened from the calendar
  const [wantIssue, setWantIssue] = useState(returned?.issue || null) // from the alert: open it once loaded
  const [planning, setPlanning] = useState(false)
  const [pane, setPane] = useState(returned?.issue ? 'attention' : 'unassigned')   // which list on the left is open
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const navigate = useNavigate()

  // Deal With It on the alert: the problem opens here as soon as the board has it.
  useEffect(() => {
    if (!wantIssue || !data) return
    const found = (data.problems || []).find((pr) => pr.recordid === wantIssue)
    if (found) setIssue(found)
    setWantIssue(null)
  }, [data, wantIssue])

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); reload() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  // Read again on its own, so a driver setting off, arriving or finishing shows up without anybody
  // pressing anything - and at once when the tab is looked at again after being in the background.
  useEffect(() => {
    const again = setInterval(() => { if (document.visibilityState === 'visible') reload() }, 15000)
    const back = () => { if (document.visibilityState === 'visible') reload() }
    document.addEventListener('visibilitychange', back)
    return () => { clearInterval(again); document.removeEventListener('visibilitychange', back) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day])

  // Dropped on a driver: that driver, in their shift's vehicle. A pairing that needs somebody's
  // say-so opens the Assign dialog, where the reason is given; a refusal is said with its reason.
  const place = (legid, driverid) => {
    const leg = data.items.find((l) => l.legid === legid)
    if (!leg || leg.driverid === driverid) return
    act(async () => {
      try { await api.post('/dispatch/place', { legid, driverid }) }
      catch (e) {
        if (e.status === 400 || e.status === 403) { setAssigning(leg); return }
        throw e
      }
    })
  }

  // A finished trip says so, whatever was reported on the way; the report itself stays on the
  // problem banner until it is dealt with.
  const status = (l) => (l.issueid && l.executionstate !== 'completed'
    ? <span className="st-expired">{SHORT[l.issuekind] || 'A problem'}</span>
    : l.outcomestate
    ? <span className="st-expired">{OUTCOME[l.outcomestate] || l.outcomestate}</span>
    : l.late
      ? <span className={l.late === 'missed' ? 'st-expired' : 'st-ordered'}>{WHATNOW[l.late]}</span>
      : l.attention ? ATTENTION[l.attention]
      : l.brokerstate === 'offered' ? 'Offered'
      : l.brokerstate === 'returnpending' ? 'Returning To Broker'
      : !l.pickupat && l.executionstate === 'scheduled' ? 'Waiting For Call'
      : SAID[l.executionstate] || l.executionstate)

  // What can be done to one leg, most pressing first - the same buttons wherever the leg is shown.
  const actions = (l, then = () => {}) => {
    const go = (fn) => (e) => { e.stopPropagation(); then(); fn() }
    const open = !l.outcomestate && l.executionstate !== 'completed'
    return (
      <span className="rowacts">
        {l.brokerstate === 'offered' ? <>
          <button type="button" className="linkbtn edit" disabled={busy}
            onClick={go(() => act(() => api.post(`/trips/${l.tripid}/accept`, {})))}>Accept</button>
          <button type="button" className="linkbtn" disabled={busy}
            onClick={go(() => setReturning(l))}>Return</button>
        </> : l.brokerstate === 'returnpending' ? (
          // Sent back and waiting on the broker: nothing to do but record that they have it.
          <button type="button" className="linkbtn edit" onClick={go(() => setConfirming(l))}>Broker Confirmed</button>
        ) : l.issueid ? (
          <button type="button" className="linkbtn"
            onClick={go(() => setIssue((data.problems || []).find((pr) => pr.recordid === l.issueid)))}>
            <AlertTriangle size={13} /> Deal With It
          </button>
        ) : l.outcomestate === 'disputed' ? (
          <button type="button" className="linkbtn" onClick={go(() => setClosing(l))}>Settle Dispute</button>
        ) : open && !l.pickupat ? (
          // Not scheduled until the passenger calls: the call gives it a time, and then a driver.
          <button type="button" className="linkbtn" onClick={go(() => setCalled(l))}>Passenger Called</button>
        ) : open && (l.late === 'missed' || (l.late && l.driverid)) ? (
          <button type="button" className="linkbtn" onClick={go(() => setClosing(l))}>What Happened</button>
        ) : open ? (
          <button type="button" className="linkbtn edit" onClick={go(() => setAssigning(l))}>
            {l.driverid ? 'Change Driver' : <><UserPlus size={13} /> Assign Driver</>}
          </button>
        ) : null}
        {!l.cancelled && !l.outcomestate && l.executionstate !== 'completed' && l.pickupat
          && !['returnpending', 'returned'].includes(l.brokerstate)
          && !['billed', 'paid'].includes(l.billingstatus) && (
          <button type="button" className="linkbtn edit" onClick={go(() => setEditing(l.tripid))}>Edit Trip</button>
        )}
        {/* A broker's trip not yet started can go back to the broker it came from. */}
        {l.broker && !['offered', 'returnpending', 'returned'].includes(l.brokerstate) && !l.cancelled
          && !l.outcomestate && l.executionstate === 'scheduled' && (
          <button type="button" className="linkbtn" onClick={go(() => setReturning(l))}>Return To Broker</button>
        )}
        {/* Back on the trip page comes here again, to this day and this trip's dialog. */}
        <button type="button" className="linkbtn edit"
          onClick={go(() => navigate(`/trips/${l.tripid}`, { state: { back: { day, legid: l.legid } } }))}>View Trip</button>
      </span>
    )
  }

  const open = (l) => !l.outcomestate && !l.cancelled && l.executionstate !== 'completed'
    && l.brokerstate !== 'returned'
  // Waiting for a driver: a pickup time, nobody on it, and still to be done.
  const waiting = (data?.items || []).filter((l) => l.pickupat && !l.driverid && open(l))
  // Will-calls: not scheduled until the passenger calls, so listed on their own, with only that
  // call to record. Once it is recorded the leg has a time and joins the unassigned trips.
  const willcalls = (data?.items || []).filter((l) => !l.pickupat && open(l))
  // Needs Attention: what is still open from an earlier day - a pickup that went by and was never
  // closed - and any dispute not settled, whatever its day. Today's late trips are on the calendar
  // already, in their colours, so they are not repeated here.
  const today = ymd(new Date())
  // A problem a driver reported comes first, whatever its day: somebody is waiting on an answer.
  const attention = (data?.attention || []).filter((l) => l.issueid || (l.pickupat && l.pickupat.slice(0, 10) < today)
    || l.outcomestate === 'disputed').sort((a, b) => Boolean(b.issueid) - Boolean(a.issueid))
  const problemOpen = attention.some((l) => l.issueid)

  // One leg as a card in the lists on the left, dragged from there onto a driver.
  const queueCard = (l) => (
    <div key={l.legid} className={['gridcarditem', tone(l), !l.pickupat && 'willcallcard'].filter(Boolean).join(' ')}
      draggable={Boolean(l.pickupat) && !['offered', 'returnpending', 'returned'].includes(l.brokerstate)}
      onDragStart={(e) => { e.dataTransfer.setData('text/leg', l.legid); e.dataTransfer.effectAllowed = 'move' }}>
      <div className="legbody">
        {/* A will-call is in the will-call list already, waiting on its call: a band saying so
            again says nothing. */}
        {l.pickupat && (
          <div className="leghead">
            {/* The date as well when it is not the day on the board: an open trip from last week. */}
            <span className="legwhen"><b>{l.pickupat.slice(0, 10) !== day ? `${date(l.pickupat)} ` : ''}{time(l.pickupat)}</b></span>
            <span className="legstatus">{status(l)}</span>
          </div>
        )}
        <div className="legwho">
          <b>{l.passenger}</b>
          <span>{(data.services || {})[l.servicelevel] || l.servicelevel}</span>
        </div>
        <span className="route">
          <span><b>FROM:</b> {l.pickupplace}</span>
          <span><b>TO:</b> {l.dropoffplace}</span>
        </span>
        {!l.pickupat && l.lastcall && (
          <div className="legnote"><b>LAST CALL {tzDateTime(l.lastcallon)}:</b> {l.lastcall.replace(/^PASSENGER CALLED - /, '')}</div>
        )}
      </div>
      <div className="legfoot">{actions(l)}</div>
    </div>
  )

  return (
    <div className="fill wide">
      {/* One row for the title, the day and every action, so the day itself gets the height. */}
      <div className="pagehead daypagehead">
        <h1>Dispatch</h1>
        <div className="segs daypick">
          <button type="button" className="chip" title="The day before" aria-label="The day before"
            onClick={() => setDay(shift(day, -1))}><ChevronLeft size={16} /></button>
          <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
          <button type="button" className="chip" title="The day after" aria-label="The day after"
            onClick={() => setDay(shift(day, 1))}><ChevronRight size={16} /></button>
        </div>
        <div className="row pushright">
          <button type="button" onClick={() => navigate('/vehicle-assignments')}>
            <CalendarRange size={14} /> Vehicle Assignments
          </button>
          {/* The screen that dispatches work is the screen that takes it in. */}
          <button type="button" className="primary" onClick={() => setBooking(true)}>
            <Plus size={14} /> Book A Trip
          </button>
        </div>
      </div>

      {err && <div className="notice bad">{err}</div>}

      {!data ? <Loading error={error} page /> : (
        <div className="dispatchday">
          {/* The two lists the day is assigned from, one open at a time so it has the height. */}
          <div className="card qualcard dispatchqueue dispatchside">
            {[['unassigned', 'Unassigned Trips', waiting,
               data.items.some((l) => l.pickupat) ? 'Every trip this day has a driver.' : 'No trips booked for this day.'],
              ['willcall', 'Will-Call Trips', willcalls, 'No will-call trips waiting on a call.'],
              ['attention', 'Needs Attention', attention, 'Nothing from earlier days needs closing.']].map(([k, title, list, none]) => (
              <Fragment key={k}>
                <button type="button" className={`infotabs accordhead${pane === k ? ' on' : ''}`}
                  aria-expanded={pane === k} onClick={() => setPane(k)}>
                  <h3>{title}{list.length > 0 && <span className={`countpill${k === 'attention' ? (problemOpen ? ' bad' : ' hot') : ''}`}>{list.length}</span>}</h3>
                  <ChevronDown size={16} />
                </button>
                {pane === k && (
                  <div className="panelbody">
                    {!list.length ? <div className="hireempty">{none}</div> : list.map(queueCard)}
                  </div>
                )}
                {pane === k && k === 'unassigned' && (
                  <footer className="panelfoot">
                    <button type="button" disabled={!waiting.some((l) => !['offered', 'returnpending'].includes(l.brokerstate))}
                      onClick={() => setPlanning(true)}><Sparkles size={14} /> Auto Assign</button>
                  </footer>
                )}
              </Fragment>
            ))}
          </div>
          <Calendar day={day} data={data} status={status} onOpen={setLooking} onPlace={place} />
        </div>
      )}

      {looking && (() => {
        const l = data?.items.find((x) => x.legid === looking)
        if (!l) return null
        return (
          <Modal width={680} title={`${l.externalid} - ${l.passenger}`} onClose={() => setLooking(null)}
            footer={<>{actions(l, () => setLooking(null))}
              <button type="button" onClick={() => setLooking(null)}>Close</button></>}>
            <div className="kv">
              <dt>Pickup</dt><dd>{l.pickupat ? `${date(l.pickupat)} ${time(l.pickupat)}` : 'Will-call'}</dd>
              <dt>Status</dt><dd>{status(l)}</dd>
              <dt>Service</dt><dd>{(data.services || {})[l.servicelevel] || l.servicelevel}</dd>
              <dt>From</dt><dd>{l.pickupplace}</dd>
              <dt>To</dt><dd>{l.dropoffplace}</dd>
              <dt>Driver</dt><dd>{l.drivername || 'None'}</dd>
              <dt>Vehicle</dt><dd>{l.vehiclename || 'None'}</dd>
              {l.detail && <><dt>What Went Wrong</dt><dd>{l.detail}</dd></>}
            </div>
          </Modal>
        )
      })()}
      {planning && (
        <AutoAssignDialog day={day} onClose={() => setPlanning(false)}
          onDone={() => { setPlanning(false); reload() }} />
      )}
      {cancelling && (
        <CancelDialog leg={cancelling} reasons={data?.cancelreasons || {}}
          onClose={() => setCancelling(null)}
          onDone={() => { setCancelling(null); reload() }} />
      )}
      {closing && (
        <WhatHappenedDialog leg={closing}
          settling={closing.outcomestate === 'disputed'}
          options={closing.outcomestate === 'disputed'
            ? Object.fromEntries(Object.entries(data?.whathappened || {}).filter(([k]) => k !== 'disputed'))
            : data?.whathappened || {}}
          onCancel={() => { const l = closing; setClosing(null); setCancelling(l) }}
          onClose={() => setClosing(null)}
          onDone={() => { setClosing(null); reload() }} />
      )}
      {issue && (
        <IssueDialog issue={issue} kinds={data?.issuekinds || {}}
          title={`A Problem On ${issue.externalid}`}
          onOut={() => { setOut({ kind: 'vehicle', who: issue.vehicleid }); setIssue(null) }}
          onReassign={() => { setAssigning({ legid: issue.legid, tripid: issue.tripid,
                                             externalid: issue.externalid }); setIssue(null) }}
          onClose={() => setIssue(null)}
          onDone={() => { setIssue(null); reload() }} />
      )}
      {out && <OutDialog start={out} onClose={() => setOut(false)}
        onDone={() => { setOut(false); reload() }} />}
      {called && (
        <PassengerCalledDialog leg={called} reasons={data?.notneeded || {}} onClose={() => setCalled(null)}
          onAssign={(l) => { setCalled(null); reload(); setAssigning(l) }}
          onDone={() => { setCalled(null); reload() }} />
      )}
      {editing && (
        <EditTrip tripid={editing} onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); reload() }} />
      )}
      {booking && (
        <BookTrip onClose={() => setBooking(false)}
          onBooked={() => { setBooking(false); reload() }} />
      )}
      {confirming && (
        <BrokerConfirmedDialog leg={confirming} onClose={() => setConfirming(null)}
          onDone={() => { setConfirming(null); reload() }} />
      )}
      {returning && (
        <ReturnDialog leg={returning} reasons={data?.returnreasons || {}}
          onClose={() => setReturning(null)}
          onDone={() => { setReturning(null); reload() }} />
      )}
      {assigning && (
        <AssignDialog leg={assigning} onClose={() => setAssigning(null)}
          onCancel={() => { const l = assigning; setAssigning(null); setCancelling(l) }}
          onDone={() => { setAssigning(null); reload() }} />
      )}
    </div>
  )
}

// One column per driver on shift that day - and per driver with trips that day but no shift, so
// work nobody planned a vehicle for is on the board rather than off it. The shift is the pale band
// down the column; the trips sit on it. A trip is a button: it opens what can be done to it.
// Each driver's own colour, in column order: on the dot by their name and the band of their day,
// so a driver can be followed down the board at a glance. Never one of the trip-state colours.
const HUES = [['#0e9fb4', '#dcf2f6'], ['#d9822b', '#fdeedd'], ['#6d4bb3', '#ece6f7'], ['#2e8b57', '#e0f2e7'],
              ['#c2416b', '#f9e3ea'], ['#2f6fd0', '#e2ecfb'], ['#a07a0a', '#f6eed2'], ['#0e8f8f', '#d9f2f2']]

function Calendar({ day, data, status, onOpen, onPlace }) {
  const [over, setOver] = useState(null)
  const head = useRef(null)
  const body = useRef(null)
  // The width of the day's own vertical scrollbar, which the names above must allow for: without
  // it the names can scroll a scrollbar's width less than the day, and drift off their columns.
  const [bar, setBar] = useState(0)
  useEffect(() => {
    const measure = () => { if (body.current) setBar(body.current.offsetWidth - body.current.clientWidth) }
    measure()
    const watch = new ResizeObserver(measure)
    if (body.current) watch.observe(body.current)
    return () => watch.disconnect()
  })
  // Where the day has got to, when the day shown is today: a line across every column, moved on
  // each minute.
  const [nowAt, setNowAt] = useState(() => new Date())
  useEffect(() => { const t = setInterval(() => setNowAt(new Date()), 60000); return () => clearInterval(t) }, [])
  const today = `${nowAt.getFullYear()}-${String(nowAt.getMonth() + 1).padStart(2, '0')}-${String(nowAt.getDate()).padStart(2, '0')}` === day
  const columns = useMemo(() => {
    const names = new Map(data.roster.drivers.map((d) => [d.driverid, d.name]))
    const byDriver = new Map()
    const col = (id, name) => {
      if (!byDriver.has(id)) byDriver.set(id, { driverid: id, name: name || names.get(id) || 'Driver', shifts: [], legs: [] })
      return byDriver.get(id)
    }
    data.roster.shifts.forEach((s) => col(s.driverid, s.drivername).shifts.push(s))
    // A will-call has no time and no place on the clock: it is in the list on the left.
    data.items.filter((l) => l.driverid && l.pickupat).forEach((l) => col(l.driverid, l.drivername).legs.push(l))
    byDriver.forEach((c) => c.shifts.sort((a, b) => minutes(a.startsat) - minutes(b.startsat)))
    return [...byDriver.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [data])

  // The company's hours that day (Company page) are the day drawn; work outside them stretches it,
  // and the stretch is shaded as out of hours. Hours not set: six to eight.
  const open = data.roster.hours?.open ? [minutes(data.roster.hours.open), ends({ startsat: data.roster.hours.open, endsat: data.roster.hours.close })] : null
  const [from, to] = useMemo(() => {
    let lo = open ? open[0] : 6 * 60
    let hi = open ? open[1] : 20 * 60
    columns.forEach((c) => {
      c.shifts.forEach((s) => { lo = Math.min(lo, minutes(s.startsat)); hi = Math.max(hi, ends(s)) })
      c.legs.forEach((l) => { lo = Math.min(lo, at(l.pickupat)); hi = Math.max(hi, at(l.expectedend || l.pickupat) + 30) })
    })
    return [Math.floor(lo / 60) * 60, Math.ceil(hi / 60) * 60]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns, data.roster.hours])
  const slots = []
  for (let m = from; m < to; m += 15) slots.push(m)
  const top = (m) => ((m - from) / 15) * SLOT

  if (!columns.length) {
    return (
      <div className="card shiftboard dispatchboard">
        <div className="gridempty">{data.roster.hours?.closed ? 'Closed this day.' : 'No driver has a vehicle assigned this day.'}</div>
      </div>
    )
  }
  const drop = (driverid) => ({
    onDragOver: (e) => { if (e.dataTransfer.types.includes('text/leg')) { e.preventDefault(); setOver(driverid) } },
    onDragLeave: () => setOver((o) => (o === driverid ? null : o)),
    onDrop: (e) => { e.preventDefault(); setOver(null); const id = e.dataTransfer.getData('text/leg'); if (id) onPlace(id, driverid) },
  })
  // The names are a row of their own above the scrolling day, so the scrollbar runs beside the
  // hours only; it follows the day sideways, so each name stays over its column.
  return (
    <div className="card shiftboard dispatchboard">
      <div className="calhead" ref={head}>
        <div className="shiftgutter"><div className="shifthead" /></div>
        {columns.map((c, n) => (
          <div key={c.driverid} className={`shiftcol${over === c.driverid ? ' droptarget' : ''}`} {...drop(c.driverid)}>
            <div className={`shifthead${c.shifts.length ? '' : ' unassigned'}`}>
              <b><span className="huedot" style={{ background: HUES[n % HUES.length][0] }} />{c.name.toUpperCase()}
                {/* A problem this driver reported that is not resolved yet. */}
                {(data.problems || []).some((pr) => pr.driverid === c.driverid) && (
                  <AlertTriangle size={15} className="drvproblem" aria-label="Problem reported" />
                )}</b>
              <GpsLine at={data.roster.gps?.[c.driverid]} now={nowAt} />
              {/* The vehicle is on the band down the column, not up here: a driver can change
                  vehicles during the day, and each band names its own. */}
              {!c.shifts.length && <span>No Vehicles Assigned To Driver For This Day</span>}
            </div>
          </div>
        ))}
        <div className="calbar" style={{ flex: `0 0 ${bar}px` }} />
      </div>
      <div className="shiftscroll calbody" ref={body}
        onScroll={(e) => { if (head.current) head.current.scrollLeft = e.currentTarget.scrollLeft }}>
        <div className="shiftgutter">
          {slots.map((m) => <div key={m} className={`shiftslot${m % 60 ? '' : ' hour'}`}>{clock(m)}</div>)}
          {/* Where the day has got to, when the day shown is today: an arrow on the time column. */}
          {today && nowAt.getHours() * 60 + nowAt.getMinutes() >= from && nowAt.getHours() * 60 + nowAt.getMinutes() < to && (
            <div className="nowarrow" style={{ top: top(nowAt.getHours() * 60 + nowAt.getMinutes()) }}
              title={`Now, ${clock(nowAt.getHours() * 60 + nowAt.getMinutes())}`} />
          )}
        </div>
        {columns.map((c, n) => (
          <div key={c.driverid} className={`shiftcol${over === c.driverid ? ' droptarget' : ''}`} {...drop(c.driverid)}
            style={{ '--hue': HUES[n % HUES.length][0], '--huebg': HUES[n % HUES.length][1] }}>
            <div className="shiftbody" style={{ height: slots.length * SLOT }}>
              {open && open[0] > from && <div className="offhours" style={{ top: 0, height: top(open[0]) }} />}
              {open && open[1] < to && <div className="offhours" style={{ top: top(open[1]), height: top(to) - top(open[1]) }} />}
              {slots.map((m) => <div key={m} className={`shiftline${m % 60 ? '' : ' hour'}`} style={{ top: top(m) }} />)}
              {c.shifts.map((s) => (
                <div key={s.recordid} className="shiftband"
                  style={{ top: top(minutes(s.startsat)), height: ((ends(s) - minutes(s.startsat)) / 15) * SLOT }}>
                  {s.vehiclename}
                </div>
              ))}
              {c.legs.map((l) => {
                // From the moment the app said the passenger was aboard (the booked pickup until
                // then) to the moment it said they arrived - or, under way, when they should.
                const a = at(l.pickedupat || l.pickupat)
                const b = l.expectedend ? Math.max(at(l.expectedend), a + 5) : a + 30
                return (
                  <button key={l.legid} type="button"
                    className={['shiftleg', tone(l), l.outcomestate || l.cancelled ? 'closed' : null].filter(Boolean).join(' ')}
                    draggable={!l.outcomestate && l.executionstate === 'scheduled'}
                    onDragStart={(e) => e.dataTransfer.setData('text/leg', l.legid)}
                    onClick={() => onOpen(l.legid)}
                    // Starts at the exact moment; never drawn too short to read, whatever it took.
                    style={{ top: top(a) + 2, height: Math.max(((b - a) / 15) * SLOT - 4, 76) }}>
                    {/* One fact a line, none of them wrapping: who; picked up; dropped off - as the app
                        reported them once they happened, the plan or the estimate (≈) until then;
                        and where it stands. */}
                    <b className="legline legwho2">{l.passenger}</b>
                    <span className="legline">{l.pickedupat ? `Picked up ${clock(a)}` : `Pickup ${clock(a)}`}</span>
                    <span className="legline">
                      {l.executionstate === 'completed' && l.dropoffat ? `Dropped off ${clock(at(l.dropoffat))}`
                        : l.eta ? `Drop-off ≈ ${clock(at(l.eta.at))}` : l.expectedend ? `Drop-off ≈ ${clock(b)}` : 'Drop-off not known'}
                    </span>
                    <span className="legline legfoot2">
                      <span className="legpill">{status(l)}</span>
                      {moving(l) && <span className="legtimes">{l.eta ? `${l.eta.minutes} min to go` : 'No GPS yet'}</span>}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Whether the office can see where this driver is: their phone's last position, and how old it is.
// Live within five minutes; last seen within two hours; older than that, or never, is no help.
function GpsLine({ at, now }) {
  if (!at) return <span className="gpsline gps-none"><i />No GPS</span>
  const mins = Math.max(0, Math.round((now - new Date(`${at.replace(' ', 'T')}Z`)) / 60000))
  const [kind, said] = mins <= 5 ? ['live', 'GPS live']
    : mins < 120 ? ['old', `GPS ${mins} min ago`]
    : ['none', mins < 2880 ? `GPS ${Math.round(mins / 60)} h ago` : `GPS ${Math.round(mins / 1440)} days ago`]
  return <span className={`gpsline gps-${kind}`}><i />{said}</span>
}

// Auto Assign: a driver for each of the day's unassigned trips, with why - and, for one that could
// not be placed, what stands in the way. Nothing is saved until Save; each assignment then passes
// the same gate as one made by hand.
function AutoAssignDialog({ day, onClose, onDone }) {
  const [proposal, setProposal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [refused, setRefused] = useState(null)
  useEffect(() => {
    api.post('/dispatch/autoplan', { day }).then((got) => setProposal(got.proposal)).catch((e) => setErr(e.message))
  }, [day])
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const got = await api.post('/dispatch/autoplan/save', {
        items: proposal.filter((p) => p.driverid).map(({ legid, driverid, vehicleid }) => ({ legid, driverid, vehicleid })),
      })
      if (got.refused.length) { setRefused(got.refused); setBusy(false) } else onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title="Auto Assign Trips" onClose={refused ? onDone : onClose} width={980} tall
      footer={refused ? <button type="button" className="primary" onClick={onDone}>Close</button> : <>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !proposal?.some((p) => p.driverid)}
          onClick={save}>{busy ? <Loader2 size={15} className="spin" /> : 'Save'}</button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {refused && <div className="notice bad">{refused.map((r) => <div key={r}>{r}</div>)}</div>}
        {!proposal ? (!err && <Loading />) : !proposal.length ? (
          <div className="muted">No unassigned trip with a pickup time this day.</div>
        ) : (
          <table className="residencetable recordtable shiftproposal">
            <thead><tr><th>Pickup</th><th>Passenger</th><th>Driver</th><th>Why</th></tr></thead>
            <tbody>
              {proposal.map((p) => (
                <tr key={p.legid}>
                  <td>{time(p.pickupat)}</td>
                  <td>{p.passenger}</td>
                  <td className={p.driverid ? undefined : 'st-expired'}>
                    {p.driverid ? `${p.drivername} · ${p.vehiclename}` : 'None'}</td>
                  <td className={p.driverid ? undefined : 'st-expired'}>
                    {(p.driverid ? p.reasons : p.blocked).join(' · ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  )
}

// Closing out a leg whose pickup time went by with nothing recorded against it - or settling one
// that was recorded as in dispute.
//
// Each answer is said with what it means, because which one it is decides who pays: a trip that
// was driven is billed, a passenger who did not come out is a no-show most broker contracts price,
// and a trip we did not do is held out of billing. In Dispute is not an ending: it says what is in
// question and stays open until somebody settles it, and settling it says on what basis.
const MEANS = {
  driven: 'The trip took place. Enter when the passenger was picked up and dropped off.',
  noshow: 'The driver went. The passenger did not come out.',
  aborted: 'The trip did not take place, and it was ours to do. It is held from billing.',
  disputed: 'We do not agree on what happened. It stays open until it is settled.',
}

function WhatHappenedDialog({ leg, options, settling, onCancel, onClose, onDone }) {
  const [outcome, setOutcome] = useState(null)
  const [note, setNote] = useState('')
  const [pickedupat, setPicked] = useState('')
  const [droppedoffat, setDropped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const driven = outcome === 'driven'
  const needsnote = settling || outcome === 'disputed'
  const ready = outcome && (!driven || droppedoffat) && (!needsnote || note.trim())
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/legs/${leg.legid}/outcome`, {
        outcome, note,
        pickedupat: driven && pickedupat ? pickedupat : null,
        droppedoffat: driven && droppedoffat ? droppedoffat : null,
      })
      onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  const d = leg.dispute
  return (
    <Modal width={680} title={`${settling ? 'Settle Dispute' : 'What Happened'} - ${leg.externalid}`} onClose={onClose}
      footer={<>
        <div className="footactions">
          <button type="button" className="danger" onClick={onCancel}>Cancel The Trip</button>
        </div>
        <button type="button" onClick={onClose}>Close</button>
        <button type="button" className="primary" disabled={busy || !ready} onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : settling ? 'Settle' : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        {settling && <>
          <h3 className="formsection">The Dispute</h3>
          <div className="kv">
            <dt>Raised By</dt><dd>{d?.raisedby || 'Not recorded'}</dd>
            <dt>Raised On</dt><dd>{d?.raisedon ? tzDateTime(d.raisedon) : 'Not recorded'}</dd>
            <dt>Reason</dt><dd>{d?.reason || 'No reason was recorded.'}</dd>
          </div>
        </>}
        <h3 className="formsection">The Trip</h3>
        <div className="kv">
          <dt>Passenger</dt><dd>{leg.passenger}</dd>
          <dt>Pickup</dt><dd>{leg.pickupat ? `${date(leg.pickupat)} ${time(leg.pickupat)}` : 'Will-call'}</dd>
          <dt>From</dt><dd>{leg.pickupplace}</dd>
          <dt>To</dt><dd>{leg.dropoffplace}</dd>
          <dt>Driver</dt><dd>{leg.drivername || 'None'}</dd>
          <dt>Vehicle</dt><dd>{leg.vehiclename || 'None'}</dd>
        </div>
        <h3 className="formsection">{settling ? 'How It Was Settled' : 'What Happened'}</h3>
        <div>
          {Object.entries(options).map(([v, l]) => (
            <label key={v} className={`tierpick${outcome === v ? ' on' : ''}`}>
              <input type="radio" name="outcome" checked={outcome === v} onChange={() => setOutcome(v)} />
              <span className="tierbody">
                <span className="tiername">{l}</span>
                <span className="tiercovers">{MEANS[v]}</span>
              </span>
            </label>
          ))}
        </div>
        <div className="profileform">
          {driven && <>
            <label className="field span-3">Picked Up At
              <input type="datetime-local" value={pickedupat}
                onChange={(e) => setPicked(e.target.value)} /></label>
            <label className="field span-3">Dropped Off At *
              <input type="datetime-local" value={droppedoffat}
                onChange={(e) => setDropped(e.target.value)} /></label>
          </>}
          <label className="field span-6">
            {settling ? 'On What Basis It Was Settled *' : outcome === 'disputed' ? 'What Is In Dispute *' : 'Note'}
            <textarea value={note} className="upper"
              onChange={(e) => setNote(e.target.value.toUpperCase())} /></label>
        </div>
      </div>
    </Modal>
  )
}

// The passenger on a will-call return has rung - which is not always to be collected. What they
// said is chosen, each with what it does: a pickup time; the call written down and the leg left
// waiting; or the return closed as not needed, with why.
const CALLS = {
  ready: ['Ready To Be Picked Up', 'The return gets a pickup time and joins the unassigned trips.'],
  notready: ['Not Ready Yet', 'The call is written down. The return goes on waiting for the next one.'],
  notneeded: ['Return Not Needed', 'The return is closed as canceled. The rest of the trip is left as it is.'],
}

function PassengerCalledDialog({ leg, reasons, onClose, onDone, onAssign }) {
  const here = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const [answer, setAnswer] = useState(null)
  const [at, setAt] = useState(`${here.getFullYear()}-${pad(here.getMonth() + 1)}-${pad(here.getDate())}T${pad(here.getHours())}:${pad(here.getMinutes())}`)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const ready = answer && (answer !== 'ready' || at)
    && (answer !== 'notneeded' || (reason && (reason !== 'other' || note.trim())))
  // `assign`: saved, and then straight on to giving the return its driver.
  const go = async (assign) => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/legs/${leg.legid}/call`, {
        answer, note, reason: answer === 'notneeded' ? reason : null,
        pickupat: answer === 'ready' ? `${at}:00` : null,
      })
      if (assign) onAssign({ ...leg, pickupat: `${at}:00` }); else onDone()
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal width={680} title={`Passenger Called - ${leg.externalid}`} onClose={onClose}
      footer={<>
        <div className="footactions">
          <button type="button" disabled={busy || !ready || answer !== 'ready'} onClick={() => go(true)}>
            <UserPlus size={13} /> Assign Driver
          </button>
        </div>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !ready} onClick={() => go(false)}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="kv">
          <dt>Passenger</dt><dd>{leg.passenger}</dd>
          <dt>From</dt><dd>{leg.pickupplace}</dd>
          <dt>To</dt><dd>{leg.dropoffplace}</dd>
          {leg.lastcall && <><dt>Last Call</dt><dd>{tzDateTime(leg.lastcallon)} - {leg.lastcall}</dd></>}
        </div>
        <h3 className="formsection">What The Passenger Said</h3>
        <div>
          {Object.entries(CALLS).map(([v, [l, means]]) => (
            <label key={v} className={`tierpick${answer === v ? ' on' : ''}`}>
              <input type="radio" name="answer" checked={answer === v} onChange={() => setAnswer(v)} />
              <span className="tierbody">
                <span className="tiername">{l}</span>
                <span className="tiercovers">{means}</span>
              </span>
            </label>
          ))}
        </div>
        <div className="profileform">
          {answer === 'ready' && (
            <label className="field span-3">Pickup Time *
              <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
            </label>
          )}
          {answer === 'notneeded' && (
            <label className="field span-3">Reason *
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                <option value="">Choose</option>
                {Object.entries(reasons).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          )}
          <label className="field span-6">{answer === 'notneeded' && reason === 'other' ? 'Note *' : 'Note'}
            <textarea value={note} className="upper" onChange={(e) => setNote(e.target.value.toUpperCase())} />
          </label>
        </div>
      </div>
    </Modal>
  )
}

// Calling a trip off. Marked, never deleted - a trip that was booked and then cancelled is a
// fact a broker will ask about, and a deleted one cannot answer.
function CancelDialog({ leg, reasons, onClose, onDone }) {
  const [reason, setReason] = useState('passenger')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try { await api.post(`/trips/${leg.tripid}/cancel`, { reason, note }); onDone() }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal width={620} title={`Cancel ${leg.externalid}`} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Keep It</button>
        <button type="button" className="primary danger" disabled={busy} onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Cancel The Trip'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice">
          The trip stays on the record, marked canceled. Any leg already driven is left as it is.
        </div>
        <div className="profileform">
          <label className="field span-6">Reason
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {Object.entries(reasons).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-6">Note
            <textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
        </div>
      </div>
    </Modal>
  )
}

// Handing one trip back to the broker it came from. The reason is chosen, not typed: the broker
// asks why in its own words, and a free-text box cannot be reported on or sent through an API.
function ReturnDialog({ leg, reasons, onClose, onDone }) {
  const [reason, setReason] = useState('drivershortage')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const send = async () => {
    setBusy(true); setErr(null)
    try { await api.post(`/trips/${leg.tripid}/return`, { reason, note }); onDone() }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal width={620} title={`Return ${leg.externalid} To The Broker`} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy} onClick={send}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Return It'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="notice">
          It stays on this board, counted as uncovered, until the broker confirms they have it. A driver on it is taken off and told.
        </div>
        <div className="profileform">
          <label className="field span-6">Reason
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {Object.entries(reasons).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field span-6">Note
            <textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
        </div>
      </div>
    </Modal>
  )
}

// The broker has confirmed they have a returned trip back. Only this closes it: until then it stays
// on the board as ours. Their reference is kept, and how it went back to them.
function BrokerConfirmedDialog({ leg, onClose, onDone }) {
  const [ref, setRef] = useState('')
  const [sentby, setSentby] = useState('portal')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try { await api.post(`/trips/${leg.tripid}/return/acknowledged`, { ref, sentby }); onDone() }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal width={560} title={`Broker Confirmed - ${leg.externalid}`} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy} onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-3">Returned By
            <select value={sentby} onChange={(e) => setSentby(e.target.value)}>
              <option value="portal">Broker portal</option>
              <option value="phone">Telephone</option>
              <option value="email">Email</option>
            </select>
          </label>
          <label className="field span-3">Broker's Reference
            <input value={ref} className="upper" onChange={(e) => setRef(e.target.value.toUpperCase())} />
          </label>
        </div>
      </div>
    </Modal>
  )
}
