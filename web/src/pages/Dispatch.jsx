import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Loader2, MapPin, Plus, Search, UserPlus, UserX } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time, tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'
import { Modal } from '../admin/common.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'
import BookTrip from '../components/BookTrip.jsx'
import IssueDialog, { ProblemBanner } from '../components/IssueDialog.jsx'
import OutDialog from '../components/OutDialog.jsx'
import AssignDialog from '../components/AssignDialog.jsx'

// The day's work, one row per LEG rather than per trip. A reservation out to a clinic and back is
// two pieces of work, often for two drivers, and a board that lists it once cannot say that the
// return is uncovered - which is the single thing a dispatcher is looking for.

// The incoming board is the same rows with the one thing that matters added: taking the work on,
// or handing it back.
// The row says who, what and where it stands; the line under it says where from and where to.
// An address does not belong in a column - cut to fit one it loses the end of the street name,
// which is the part a dispatcher is reading it for.
const COLUMNS = [
  { id: 'tripdate', label: 'Date', width: 110 },
  { id: 'pickupat', label: 'Time', width: 100 },
  { id: 'passenger', label: 'Passenger', width: 230 },
  { id: 'servicelevel', label: 'Service', width: 190 },
  { id: 'drivername', label: 'Driver', width: 170 },
  { id: 'vehiclename', label: 'Vehicle', width: 130 },
  { id: 'executionstate', label: 'Status', width: 160 },
]

// eslint-disable-next-line no-import-assign
const INCOMING = [...COLUMNS, { id: 'act', label: '', srLabel: 'Actions', width: 170, sortable: false }]

const FILTERS = [['attention', 'Needs attention'], ['needsdriver', 'Needs a driver'],
                 ['incoming', 'Incoming'], ['assigned', 'Assigned'], ['willcall', 'Will-call'],
                 ['returning', 'Going back'], ['', 'All']]

// Why a trip is not going to happen. The server holds the list; this is only how it is offered.
const CANCELLED = 'cancelled'



// The database's word for where a leg has got to, in the words an office uses out loud.
const SAID = {
  scheduled: 'Scheduled', enroute: 'En route', arrived: 'At pickup',
  onboard: 'Passenger aboard', completed: 'Completed',
}
const OUTCOME = { cancelled: 'Cancelled', noshow: 'No-show', aborted: 'Aborted', disputed: 'Disputed' }

// A missed pickup is a question, not an answer. "Missed" means only that the hour went by and
// nobody pressed anything - the driver may have been there and forgotten the app, the passenger
// may not have come out, or the trip may simply never have been driven. Those three are paid
// differently, so the board asks rather than guesses.
const WHATNOW = { missed: 'Missed', late: 'Running late' }

// The same problems the driver's app offers, in the width a column has. The sentence belongs in
// the dialog, where there is room to read it.
const SHORT = {
  noshow: 'No-show', refused: 'Ride refused', address: 'Bad address', vehicle: 'Vehicle problem',
  medical: 'Medical', traffic: 'Held up', equipment: 'Equipment', other: 'A problem',
}

export default function Dispatch() {
  const g = useGridParams({ filters: ['state', 'day'], defaultSort: 'pickupat', defaultDir: 'asc' })
  const state = g.filters.state === undefined ? 'needsdriver' : g.filters.state
  const query = g.query.includes('state=') ? g.query : `${g.query}&state=${state}`
  const [data, error, reload] = useLoad(() => api.get(`/dispatch/board?${query}`), [query])
  const [assigning, setAssigning] = useState(null)
  const [returning, setReturning] = useState(null)
  const [cancelling, setCancelling] = useState(null)
  const [closing, setClosing] = useState(null)
  const [issue, setIssue] = useState(null)
  const [out, setOut] = useState(false)
  const [booking, setBooking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { await fn(); reload() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const navigate = useNavigate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])

  return (
    <div className="fill">
      <div className="pagehead">
        <div><h1>Dispatch</h1></div>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Trips"
            value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          {/* The contingency, reached from the board - that is where somebody is standing
              when the telephone rings at six in the morning. */}
          <button type="button" onClick={() => setOut(true)}>
            <UserX size={14} /> Someone Is Out
          </button>
          {/* The screen that dispatches work is the screen that takes it in. A dispatcher
              answering the telephone should not have to go to another page to write it down. */}
          <button type="button" className="primary" onClick={() => setBooking(true)}>
            <Plus size={14} /> Book A Trip
          </button>
        </div>
      </div>

      <div className="filterrow">
        {FILTERS.map(([v, l]) => (
          <button key={v || 'all'} type="button"
            className={`chip${state === v ? ' on' : ''}${v === 'attention' && data?.attention ? ' shouting' : ''}`}
            onClick={() => g.setFilter('state', v)}>
            {l}{v === 'attention' && data?.attention ? ` (${data.attention})` : ''}
          </button>
        ))}
        {/* A board with no day on it is a board of everything, which is right the first time it is
            opened and wrong every time afterwards. */}
        <input type="date" value={g.filters.day || ''}
          onChange={(e) => g.setFilter('day', e.target.value)} />
        {g.filters.day && (
          <button type="button" onClick={() => g.setFilter('day', '')}>Any day</button>
        )}
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

      <DataGrid columns={state === 'incoming' ? INCOMING : COLUMNS} rows={data?.items} rowKey={(l) => l.legid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        onRowClick={(l) => navigate(`/trips/${l.tripid}`)}
        pager={data && g.pager(data.total, 'leg')}
        empty={!data?.anywork ? 'No trips booked yet. Book A Trip starts one.'
          : state === 'needsdriver' ? 'Every leg has a driver.'
            : state === 'incoming' ? 'No trips are waiting to be accepted.'
              : 'Nothing to dispatch.'}
        subrow={(l) => (
          <span className="route">
            <span><b>FROM:</b> {l.pickupplace}</span>
            <span><b>TO:</b> {l.dropoffplace}</span>
          </span>
        )}
        cells={(l) => [
          l.pickupat ? date(l.pickupat) : <span className="muted">-</span>,
          l.pickupat ? <b>{time(l.pickupat)}</b> : <span className="st-ordered">Will-call</span>,
          l.passenger,
          (data.services || {})[l.servicelevel] || l.servicelevel,
          // The driver cell IS the control. The row that asks for a driver is the row that
          // gives it one, rather than sending somebody to another screen to do it.
          <button type="button" className="linkbtn edit"
            onClick={(e) => { e.stopPropagation(); setAssigning(l) }}>
            {l.drivername || <><UserPlus size={13} /> Assign</>}
          </button>,
          l.vehiclename || <span className="muted">-</span>,
          // Cancelled beats everything; then how late it is, because a pickup time that has
          // gone by is the thing a dispatcher has to act on before anything else on the row.
          l.issueid
            ? <button type="button" className="linkbtn st-expired"
                onClick={(e) => {
                  e.stopPropagation()
                  setIssue((data.problems || []).find((pr) => pr.recordid === l.issueid))
                }}>
                <AlertTriangle size={13} /> {SHORT[l.issuekind] || 'A problem'}
              </button>
            : l.outcomestate
            ? <span className="st-expired">{OUTCOME[l.outcomestate] || l.outcomestate}</span>
            // The status cell IS the control on a leg that did not go to plan, the same way the
            // driver cell is the control on one with nobody on it. A row that says "Missed" and
            // cannot be acted on is a row that stays on the board for ever.
            : l.late
              ? <button type="button"
                  className={`linkbtn ${l.late === 'missed' ? 'st-expired' : 'st-ordered'}`}
                  onClick={(e) => { e.stopPropagation(); setClosing(l) }}>
                  {WHATNOW[l.late]}
                </button>
              : SAID[l.executionstate] || l.executionstate,
          // Only on the incoming board, where taking the work on or handing it back is the
          // whole of the job.
          ...(state === 'incoming' ? [
            <span className="rowacts">
              <button type="button" className="linkbtn edit" disabled={busy}
                onClick={(e) => { e.stopPropagation(); act(() => api.post(`/trips/${l.tripid}/accept`, {})) }}>
                Accept
              </button>
              <button type="button" className="linkbtn" disabled={busy}
                onClick={(e) => { e.stopPropagation(); setReturning(l) }}>Return</button>
            </span>,
          ] : []),
        ]} />

      {cancelling && (
        <CancelDialog leg={cancelling} reasons={data?.cancelreasons || {}}
          onClose={() => setCancelling(null)}
          onDone={() => { setCancelling(null); reload() }} />
      )}
      {closing && (
        <WhatHappenedDialog leg={closing} options={data?.whathappened || {}}
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

// Closing out a leg whose pickup time went by with nothing recorded against it.
//
// Four answers, and only one of them is good news. "It was driven" is not an outcome at all - the
// trip happened and the record of it is what is missing, so the office types the times in and the
// leg completes like any other. The other three say the work did not happen, and which one it was
// decides who pays: a passenger who did not come out is a no-show, which most broker contracts
// price; a trip nobody drove is the company's own failure and is held out of billing.
function WhatHappenedDialog({ leg, options, onCancel, onClose, onDone }) {
  const [outcome, setOutcome] = useState('noshow')
  const [note, setNote] = useState('')
  const [pickedupat, setPicked] = useState('')
  const [droppedoffat, setDropped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const driven = outcome === 'driven'
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
  return (
    <Modal width={620} title={`What Happened - ${leg.externalid}`} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Close</button>
        <button type="button" className="danger" onClick={onCancel}>Cancel The Trip</button>
        <button type="button" className="primary" disabled={busy || (driven && !droppedoffat)}
          onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Save'}
        </button>
      </>}>
      <div className="stack">
        {err && <div className="notice bad">{err}</div>}
        <div className="profileform">
          <label className="field span-6">Outcome
            <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              {Object.entries(options).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          {driven && <>
            <label className="field span-3">Picked Up At
              <input type="datetime-local" value={pickedupat}
                onChange={(e) => setPicked(e.target.value)} /></label>
            <label className="field span-3">Dropped Off At
              <input type="datetime-local" value={droppedoffat}
                onChange={(e) => setDropped(e.target.value)} /></label>
          </>}
          <label className="field span-6">Note
            <textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
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
          The trip stays on the record, marked cancelled. Any leg already driven is left as it is.
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
