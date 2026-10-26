import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, ChevronRight, LayoutGrid, List, Loader2, MapPin, Plus, Search, UserPlus, UserX } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time, tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import BookTrip from '../components/BookTrip.jsx'
import IssueDialog, { ProblemBanner } from '../components/IssueDialog.jsx'
import OutDialog from '../components/OutDialog.jsx'
import AssignDialog from '../components/AssignDialog.jsx'
import EditTrip from '../components/EditTrip.jsx'

// The day's work, one row per LEG rather than per trip. A reservation out to a clinic and back is
// two pieces of work, often for two drivers, and a board that lists it once cannot say that the
// return is uncovered - which is the single thing a dispatcher is looking for.

// The incoming board is the same rows with the one thing that matters added: taking the work on,
// or handing it back.
// The row says who, what and where it stands; the line under it says where from and where to.
// An address does not belong in a column - cut to fit one it loses the end of the street name,
// which is the part a dispatcher is reading it for.
// Every row ends in the things that can be done to it, as buttons with their names on. Nothing
// on this board is done by clicking a name or a status and hoping: a dispatcher should never have
// to guess that "Missed" opens anything.
const COLUMNS = [
  { id: 'tripdate', label: 'Date', width: 105 },
  { id: 'pickupat', label: 'Time', width: 90 },
  { id: 'passenger', label: 'Passenger', width: 170 },
  { id: 'servicelevel', label: 'Service', width: 110 },
  { id: 'drivername', label: 'Driver', width: 175 },
  { id: 'vehiclename', label: 'Vehicle', width: 110 },
  { id: 'executionstate', label: 'Status', width: 150 },
  { id: 'act', label: 'Actions', width: 365, sortable: false, className: 'actions' },
]

const FILTERS = [['', 'All'], ['attention', 'Needs Attention'], ['needsdriver', 'Needs A Driver'],
                 ['incoming', 'Incoming'], ['assigned', 'Assigned'], ['willcall', 'Will-Call'],
                 ['returning', 'Returned To Broker']]

// Why a trip is not going to happen. The server holds the list; this is only how it is offered.
const CANCELLED = 'cancelled'



// The database's word for where a leg has got to, in the words an office uses out loud.
const SAID = {
  scheduled: 'Scheduled', enroute: 'En route', arrived: 'At pickup',
  onboard: 'Passenger aboard', completed: 'Completed',
}
const OUTCOME = { cancelled: 'Canceled', noshow: 'No-show', aborted: 'Aborted', disputed: 'Disputed' }

// A missed pickup is a question, not an answer. "Missed" means only that the hour went by and
// nobody pressed anything - the driver may have been there and forgotten the app, the passenger
// may not have come out, or the trip may simply never have been driven. Those three are paid
// differently, so the board asks rather than guesses.
const WHATNOW = { missed: 'Missed', late: 'Running late' }
// On Needs Attention for a reason the row would not otherwise show: nobody on a pickup that is
// under two hours away, or a driver taken off and nobody put back.
const ATTENTION = { nodriver: 'No Driver', reassign: 'Needs Reassigning' }

// The same problems the driver's app offers, in the width a column has. The sentence belongs in
// the dialog, where there is room to read it.
const SHORT = {
  noshow: 'No-show', refused: 'Ride refused', address: 'Bad address', vehicle: 'Vehicle problem',
  medical: 'Medical', traffic: 'Held up', equipment: 'Equipment', other: 'A problem',
}

// A day as the date field holds it, and the day either side of it.
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const shift = (day, n) => { const [y, m, d] = day.split('-').map(Number); return ymd(new Date(y, m - 1, d + n)) }

export default function Dispatch() {
  const g = useGridParams({ filters: ['state', 'day'], defaultSort: 'pickupat', defaultDir: 'asc' })
  const state = g.filters.state === undefined ? 'needsdriver' : g.filters.state
  // The board is a day's work, and the day is today unless somebody steps to another. Needs
  // Attention is the exception: what is wrong is wrong whichever day it belongs to, and its count
  // is of every day - so it ignores the date rather than hiding yesterday's missed pickup.
  const day = g.filters.day || ymd(new Date())
  const dated = state !== 'attention'
  const base = g.query.split('&').filter((p) => !p.startsWith('day=')).join('&')
  const query = `${base.includes('state=') ? base : `${base}&state=${state}`}${dated ? `&day=${day}` : ''}`
  const [data, error, reload] = useLoad(() => api.get(`/dispatch/board?${query}`), [query])
  const [assigning, setAssigning] = useState(null)
  const [returning, setReturning] = useState(null)
  const [cancelling, setCancelling] = useState(null)
  const [closing, setClosing] = useState(null)
  const [issue, setIssue] = useState(null)
  const [out, setOut] = useState(false)
  const [booking, setBooking] = useState(false)
  const [editing, setEditing] = useState(null)
  const [called, setCalled] = useState(null)       // the will-call leg whose passenger has rung
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  // List or cards: how this dispatcher likes to read the board, kept in their own browser.
  const [view, setView] = useState(() => { try { return localStorage.getItem('dispatchview') || 'list' } catch { return 'list' } })
  const pickView = (v) => { setView(v); try { localStorage.setItem('dispatchview', v) } catch { /* private window */ } }

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); reload() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const navigate = useNavigate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])
  // Read again on its own, so a driver setting off, arriving or finishing shows up without anybody
  // pressing anything - and at once when the tab is looked at again after being in the background.
  useEffect(() => {
    const again = setInterval(() => { if (document.visibilityState === 'visible') reload() }, 15000)
    const back = () => { if (document.visibilityState === 'visible') reload() }
    document.addEventListener('visibilitychange', back)
    return () => { clearInterval(again); document.removeEventListener('visibilitychange', back) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  // What can be done to one leg, most pressing first. A problem the driver reported, then a
  // pickup that went by, then whether it has a driver; the work offered by a broker is taken on
  // or handed back before anything else can happen to it. A finished leg only has its trip.
  // Where the leg stands, in a word. The same word on a row and on a card.
  const status = (l) => (l.issueid
    ? <span className="st-expired">{SHORT[l.issuekind] || 'A problem'}</span>
    : l.outcomestate
    ? <span className="st-expired">{OUTCOME[l.outcomestate] || l.outcomestate}</span>
    : l.late
      ? <span className={l.late === 'missed' ? 'st-expired' : 'st-ordered'}>{WHATNOW[l.late]}</span>
      : l.attention ? ATTENTION[l.attention]
      : SAID[l.executionstate] || l.executionstate)

  // One leg as a card: when and who at the top, where from and to, what is on it, what went
  // wrong, and the buttons along the foot - the same facts and the same actions as its row.
  const legCard = (l) => (
    <>
      <div className="legbody">
        <div className="leghead">
          <span className="legwhen">
            {l.pickupat ? <><b>{time(l.pickupat)}</b> {date(l.pickupat)}</> : <b>Will-call</b>}
          </span>
          <span className="legstatus">{status(l)}</span>
        </div>
        <div className="legwho">
          <b>{l.passenger}</b>
          <span>{(data.services || {})[l.servicelevel] || l.servicelevel}</span>
        </div>
        <span className="route">
          <span><b>FROM:</b> {l.pickupplace}</span>
          <span><b>TO:</b> {l.dropoffplace}</span>
        </span>
        <div className="legcrew">
          <span><b>DRIVER:</b> {l.drivername || '-'}</span>
          <span><b>VEHICLE:</b> {l.vehiclename || '-'}</span>
        </div>
        {l.detail && <div className="legnote">{l.detail}</div>}
      </div>
      <div className="legfoot">{actions(l)}</div>
    </>
  )

  const actions = (l) => {
    const stop = (fn) => (e) => { e.stopPropagation(); fn() }
    const open = !l.outcomestate && l.executionstate !== 'completed'
    return (
      <span className="rowacts">
        {l.brokerstate === 'offered' ? <>
          <button type="button" className="linkbtn edit" disabled={busy}
            onClick={stop(() => act(() => api.post(`/trips/${l.tripid}/accept`, {})))}>Accept</button>
          <button type="button" className="linkbtn" disabled={busy}
            onClick={stop(() => setReturning(l))}>Return</button>
        </> : l.issueid ? (
          <button type="button" className="linkbtn"
            onClick={stop(() => setIssue((data.problems || []).find((pr) => pr.recordid === l.issueid)))}>
            <AlertTriangle size={13} /> Deal With Problem
          </button>
        ) : l.outcomestate === 'disputed' ? (
          // Disputed is an open question, not an ending: it stays here until somebody settles it.
          <button type="button" className="linkbtn" onClick={stop(() => setClosing(l))}>
            Settle Dispute
          </button>
        ) : open && !l.pickupat ? <>
          {/* A will-call waits for the passenger to ring. That call is what this button records,
              and it is what turns the leg into an ordinary one with a time on the board. */}
          <button type="button" className="linkbtn" onClick={stop(() => setCalled(l))}>
            Passenger Called
          </button>
          <button type="button" className="linkbtn edit" onClick={stop(() => setAssigning(l))}>
            {l.driverid ? 'Change Driver' : <><UserPlus size={13} /> Assign Driver</>}
          </button>
        </> : open && (l.late === 'missed' || (l.late && l.driverid)) ? (
          <button type="button" className="linkbtn" onClick={stop(() => setClosing(l))}>
            What Happened
          </button>
        ) : open ? (
          <button type="button" className="linkbtn edit" onClick={stop(() => setAssigning(l))}>
            {l.driverid ? 'Change Driver' : <><UserPlus size={13} /> Assign Driver</>}
          </button>
        ) : null}
        {/* Offered wherever the trip can still be put right; what may change at its stage is
            the dialog's to say. Billed, cancelled or handed back, there is nothing to offer. */}
        {!l.cancelled && !l.outcomestate && l.executionstate !== 'completed' && l.pickupat
          && !['returnpending', 'returned'].includes(l.brokerstate)
          && !['billed', 'paid'].includes(l.billingstatus) && (
          <button type="button" className="linkbtn edit" onClick={stop(() => setEditing(l.tripid))}>
            Edit Trip
          </button>
        )}
        <button type="button" className="linkbtn edit"
          onClick={stop(() => navigate(`/trips/${l.tripid}`))}>View Trip</button>
      </span>
    )
  }

  return (
    <div className="fill">
      <div className="pagehead">
        <div><h1>Dispatch</h1></div>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Trips"
            value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          {/* The screen that dispatches work is the screen that takes it in. A dispatcher
              answering the telephone should not have to go to another page to write it down. */}
          <button type="button" className="primary" onClick={() => setBooking(true)}>
            <Plus size={14} /> Book A Trip
          </button>
        </div>
      </div>

      <div className="filterrow threeway">
        {/* A board with no day on it is a board of everything, which is right the first time it is
            opened and wrong every time afterwards. */}
        <div className="filterday">
          <div className={`segs daypick${dated ? '' : ' off'}`}>
            <button type="button" className="chip" disabled={!dated} title="The day before"
              aria-label="The day before" onClick={() => g.setFilter('day', shift(day, -1))}>
              <ChevronLeft size={16} />
            </button>
            <input type="date" value={day} disabled={!dated}
              onChange={(e) => e.target.value && g.setFilter('day', e.target.value)} />
            <button type="button" className="chip" disabled={!dated} title="The day after"
              aria-label="The day after" onClick={() => g.setFilter('day', shift(day, 1))}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        <div className="segs">
          {FILTERS.map(([v, l]) => (
            <button key={v || 'all'} type="button"
              className={`chip${state === v ? ' on' : ''}${v === 'attention' && data?.attention ? ' shouting' : ''}`}
              onClick={() => g.setFilter('state', v)}>
              {l}{v === 'attention' && data?.attention ? <span className="segcount">{data.attention}</span> : null}
            </button>
          ))}
        </div>
        <div className="filterout">
          <div className="segs viewpick">
            {[['list', 'List', List], ['cards', 'Cards', LayoutGrid]].map(([v, l, Icon]) => (
              <button key={v} type="button" className={`chip${view === v ? ' on' : ''}`}
                title={l} aria-label={l} onClick={() => pickView(v)}><Icon size={16} /></button>
            ))}
          </div>
          {/* The contingency, reached from the board - that is where somebody is standing
              when the telephone rings at six in the morning. */}
          <button type="button" onClick={() => setOut(true)}>
            <UserX size={14} /> Someone Is Out
          </button>
        </div>
      </div>

      {err && <div className="notice bad">{err}</div>}

      {/* A number in a chip does not tell anybody that a driver is standing on a hard shoulder,
          so it is said out loud, on every board, for as long as nobody has dealt with it.
          What changes between boards is the BUTTON: somewhere the row cannot be seen it has to
          offer a way to it, and on a board already showing the row it would only be pointing at
          something the dispatcher is looking at - so the strip goes quiet and stays thin. */}
      {(data?.problems || []).map((pr) => (
        <ProblemBanner key={pr.recordid} issue={pr} kinds={data.issuekinds}>
          <button type="button" className="pushright" onClick={() => setIssue(pr)}>
            <AlertTriangle size={14} /> Deal With It
          </button>
        </ProblemBanner>
      ))}

      <DataGrid columns={COLUMNS} className="dispatchgrid"
        card={view === 'cards' ? legCard : undefined} rows={data?.items} rowKey={(l) => l.legid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        // A missed pickup is the whole row in red, a late one or one needing attention the warning
        // colour, one under way blue and a finished one green, so it is seen from across the room.
        rowClass={(l) => (l.unseen ? (l.executionstate === 'onboard' ? 'rowbad' : 'rowwarn')
          : l.outcomestate === 'disputed' ? 'rowwarn' : l.outcomestate || l.issueid ? null
          : l.late === 'missed' ? 'rowbad' : l.late || l.attention ? 'rowwarn'
          : l.executionstate === 'completed' ? 'rowgood'
          : ['enroute', 'arrived', 'onboard'].includes(l.executionstate) ? 'rowmoving' : null)}
        pager={data && g.pager(data.total, 'leg')}
        empty={!data?.anywork ? 'No trips booked yet. Book A Trip starts one.'
          : state === 'needsdriver' ? 'Every leg has a driver.'
            : state === 'incoming' ? 'No trips are waiting to be accepted.'
              : 'Nothing to dispatch.'}
        subrow={(l) => (
          <span className="legunder">
            <span className="route">
              <span><b>FROM:</b> {l.pickupplace}</span>
              <span><b>TO:</b> {l.dropoffplace}</span>
            </span>
            {/* What went wrong, said in full, under the Status that names it in a word. */}
            {l.detail && <span className="legdetail">{l.detail}</span>}
          </span>
        )}
        cells={(l) => [
          l.pickupat ? date(l.pickupat) : <span className="muted">-</span>,
          l.pickupat ? <b>{time(l.pickupat)}</b> : <span className="st-ordered">Will-call</span>,
          l.passenger,
          (data.services || {})[l.servicelevel] || l.servicelevel,
          l.drivername || <span className="muted">-</span>,
          l.vehiclename || <span className="muted">-</span>,
          // Cancelled beats everything; then how late it is, because a pickup time that has
          // gone by is the thing a dispatcher has to act on before anything else on the row.
          status(l),
          actions(l),
        ]} />

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
        onDone={() => { setOut(false); g.setFilter('state', 'attention'); reload() }} />}
      {called && (
        <PassengerCalledDialog leg={called} onClose={() => setCalled(null)}
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

// The passenger on a will-call return has rung. The time is when they are to be collected - now,
// unless they asked for later - and a driver already on the leg is told to go.
function PassengerCalledDialog({ leg, onClose, onDone }) {
  const here = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const [at, setAt] = useState(`${here.getFullYear()}-${pad(here.getMonth() + 1)}-${pad(here.getDate())}T${pad(here.getHours())}:${pad(here.getMinutes())}`)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try { await api.post(`/legs/${leg.legid}/release`, { pickupat: `${at}:00`, note }); onDone() }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal width={620} title={`Passenger Called - ${leg.externalid}`} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !at} onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="kv">
          <dt>Passenger</dt><dd>{leg.passenger}</dd>
          <dt>From</dt><dd>{leg.pickupplace}</dd>
          <dt>To</dt><dd>{leg.dropoffplace}</dd>
          <dt>Driver</dt><dd>{leg.drivername || 'None yet'}</dd>
        </div>
        <div className="profileform">
          <label className="field span-3">Pickup Time *
            <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </label>
          <label className="field span-6">Note
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
          It stays on this board, counted as uncovered, until the broker confirms they have it.
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
