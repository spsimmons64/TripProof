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
const WINDOWS = { rest: 'The rest of today', today: 'All of today', week: 'The next seven days' }

export default function OutDialog({ start, onClose, onDone }) {
  const [data, error] = useLoad(() => api.get('/dispatch/out'), [])
  const [people] = useLoad(() => api.get('/drivers?pagesize=200'), [])
  const [vans] = useLoad(() => api.get('/vehicles'), [])
  // Reached from a driver's own report as often as from the telephone, and arriving that way it
  // already knows which van is off the road.
  const from = typeof start === 'object' && start ? start : null
  const [kind, setKind] = useState(from?.kind || 'driver')
  const [recordid, setWho] = useState(from?.who || '')
  const [span, setSpan] = useState('today')
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
    const start = span === 'rest' ? now : new Date(new Date(now).setHours(0, 0, 0, 0))
    const until = span === 'week'
      ? new Date(new Date(midnight).setDate(midnight.getDate() + 7)) : midnight
    const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 19)
    return { fromat: iso(start), untilat: iso(until) }
  }

  const go = async () => {
    setBusy(true); setErr(null)
    try { setLifted(await api.post('/dispatch/out', { kind, recordid, reason, note, ...window() })) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const choices = kind === 'driver'
    ? (people?.items || []).map((d) => [d.recordid, `${d.firstname} ${d.lastname}`.trim()])
    : (vans || []).map((v) => [v.recordid, [v.externalid, v.make, v.model].filter(Boolean).join(' · ')])

  if (lifted) {
    return (
      <Modal width={620} title="Taken Off" onClose={onDone}
        footer={<button type="button" className="primary" onClick={onDone}>See What Needs Cover</button>}>
        <div className="stack">
          <div className="notice">
            {lifted.lifted === 0
              ? 'Nothing was assigned to them in that time, so nothing came off.'
              : `${lifted.lifted} trip${lifted.lifted === 1 ? '' : 's'} came off and need somebody.`}
          </div>
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
    <Modal width={620} title="Someone Is Out" onClose={onClose}
      footer={<>
        <button type="button" onClick={onClose}>Cancel</button>
        <button type="button" className="primary" disabled={busy || !recordid} onClick={go}>
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
            <label className="field span-3">For how long
              <select value={span} onChange={(e) => setSpan(e.target.value)}>
                {Object.entries(WINDOWS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="field span-3">Why
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                {Object.entries(data.reasons).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="field span-6">Note
              <textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
          </div>
          <div className="notice">
            Their trips in that time come off and go to Needs Attention. Nothing is given to
            anybody else automatically.
          </div>
        </div>
      )}
    </Modal>
  )
}
