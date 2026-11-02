import { useState } from 'react'
import { Loader2, UserPlus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date, time } from '../lib/format.js'
import { Loading, useLoad } from './ui.jsx'
import { Modal } from '../admin/common.jsx'

// Somebody or something is out, and everything that follows from it.
//
// One action, because that is how it arrives: a telephone call saying a driver is sick, and
// eleven trips that are suddenly nobody's. What it does NOT do is find them new drivers - who
// takes the 10:15 is a judgement about a person's day, and a system that quietly moved eleven
// trips to whoever was nearest would be making that judgement eleven times unasked.
const WINDOWS = { rest: 'The rest of today', until: 'Out until a time', today: 'All of today', week: 'The next seven days' }

// Two hours from now, on the quarter hour: where Back At starts.
const later = () => {
  const d = new Date(Date.now() + 2 * 3600000)
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function OutDialog({ start, onClose, onDone }) {
  const [data, error] = useLoad(() => api.get('/dispatch/out'), [])
  const [people] = useLoad(() => api.get('/drivers?pagesize=200'), [])
  const [vans] = useLoad(() => api.get('/vehicles'), [])
  // Reached from a driver's own report as often as from the telephone, and arriving that way it
  // already knows which van is off the road.
  const from = typeof start === 'object' && start ? start : null
  const [kind, setKind] = useState(from?.kind || 'driver')
  const [recordid, setWho] = useState(from?.who || '')
  // From a driver's column on the calendar: the rest of today, from now.
  const [span, setSpan] = useState(from?.span || 'today')
  const [backat, setBackat] = useState(later)      // out until a time: when they are back today
  const [reason, setReason] = useState(from?.kind === 'vehicle' ? 'breakdown' : 'sick')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [lifted, setLifted] = useState(null)

  // Local wall clock, sent as the operator's own time: "the rest of today" ends at midnight
  // where the vehicles are, not at midnight UTC.
  const window = () => {
    const now = new Date()
    const midnight = new Date(now); midnight.setHours(23, 59, 59, 0)
    const start = span === 'rest' || span === 'until' ? now : new Date(new Date(now).setHours(0, 0, 0, 0))
    const [bh, bm] = backat.split(':').map(Number)
    const until = span === 'week' ? new Date(new Date(midnight).setDate(midnight.getDate() + 7))
      : span === 'until' ? new Date(new Date(now).setHours(bh, bm, 0, 0)) : midnight
    const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 19)
    return { fromat: iso(start), untilat: iso(until) }
  }

  const go = async () => {
    setBusy(true); setErr(null)
    try { setLifted(await api.post('/dispatch/out', { kind, recordid, reason, note, ...window() })) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // Back At has to be later today than now.
  const backOk = span !== 'until' || (backat && (() => {
    const [bh, bm] = backat.split(':').map(Number); const n = new Date()
    return bh * 60 + bm > n.getHours() * 60 + n.getMinutes()
  })())
  const choices = kind === 'driver'
    ? (people?.items || []).map((d) => [d.recordid, `${d.firstname} ${d.lastname}`.trim()])
    : (vans || []).map((v) => [v.recordid, [v.externalid, v.make, v.model].filter(Boolean).join(' · ')])

  if (lifted) {
    return (
      <Modal width={620} title="Taken Off" onClose={() => onDone(lifted)}
        footer={<button type="button" className="primary" onClick={() => onDone(lifted)}>See What Needs Cover</button>}>
        <div className="stack">
          <div className="notice">
            {lifted.lifted === 0
              ? 'Nothing was assigned to them in that time, so nothing came off.'
              : `${lifted.lifted} trip${lifted.lifted === 1 ? '' : 's'} came off and need somebody.`}
          </div>
          {/* Their vehicle, free for whoever covers - in Vehicle Assignments. */}
          {lifted.freed?.map((v) => (
            <div key={v.vehicleid + v.from} className="notice">
              {v.vehiclename} is free from {time(v.from)}{v.until.slice(11, 16) < '23:59' ? ` until ${time(v.until)}` : ''} for whoever covers.
            </div>
          ))}
          {/* On call while out: off the On Call List, so no return is left with them. */}
          {lifted.offcall?.map((o) => (
            <div key={o.recordid} className="notice bad">
              {o.drivername} ({o.vehiclename}) was taken off the On Call List from {time(o.from)}.
            </div>
          ))}
          {/* Somebody already in the vehicle cannot be taken off it by a button: whoever is out
              has to finish this one, or somebody goes to them. */}
          {lifted.aboard?.length > 0 && (
            <div className="notice bad">
              {lifted.aboard.map((x) => (
                <div key={x.legid}>{x.passenger} is aboard now ({x.externalid}, picked up {time(x.pickupat)}). This trip is still theirs.</div>
              ))}
            </div>
          )}
          {lifted.trips.length > 0 && (
            <table className="residencetable recordtable">
              <thead><tr><th>Pickup</th><th>Trip</th><th>Passenger</th></tr></thead>
              <tbody>{lifted.trips.map((x) => (
                <tr key={x.legid}>
                  <td>{time(x.pickupat)} {date(x.pickupat)}</td>
                  <td>{x.externalid}</td><td>{x.passenger}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </Modal>
    )
  }

  return (
    <Modal width={620} title={kind === 'driver' ? 'Driver Out' : 'Vehicle Out'} onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !recordid || !backOk} onClick={go}>
          {busy ? <Loader2 size={15} className="spin" /> : 'Take Them Off'}
        </button>
      </>}>
      {!data ? <Loading error={error} /> : (
        <div className="stack">
          {err && <div className="notice bad">{err}</div>}
          <div className="filterrow">
            {[['driver', 'A driver'], ['vehicle', 'A vehicle']].map(([v, l]) => (
              <button key={v} type="button" className={`chip${kind === v ? ' on' : ''}`}
                onClick={() => { setKind(v); setWho(''); setReason(v === 'driver' ? 'sick' : 'breakdown') }}>
                {l}
              </button>
            ))}
          </div>
          <div className="profileform">
            <label className="field span-6">{kind === 'driver' ? 'Driver' : 'Vehicle'}
              <select value={recordid} onChange={(e) => setWho(e.target.value)}>
                <option value="">Choose…</option>
                {choices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className={`field ${span === 'until' ? 'span-2' : 'span-3'}`}>For How Long
              <select value={span} onChange={(e) => setSpan(e.target.value)}>
                {Object.entries(WINDOWS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            {span === 'until' && (
              <label className="field span-2">Back At *
                <input type="time" value={backat} onChange={(e) => setBackat(e.target.value)} />
              </label>
            )}
            <label className={`field ${span === 'until' ? 'span-2' : 'span-3'}`}>Why
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                {Object.entries(data.reasons).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="field span-6">Note
              <textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
          </div>
          <div className="notice">
            Their trips in that time come off and go back to Unassigned Trips. Nothing is given to
            anybody else automatically.
          </div>
        </div>
      )}
    </Modal>
  )
}
