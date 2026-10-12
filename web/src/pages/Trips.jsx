import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { count, date, money } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'
import BookTrip from '../components/BookTrip.jsx'

// The pre-billing scrub: filter to unbilled + at risk and fix each one before it goes out the door.
export default function Trips() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const status = params.get('status') || 'fail'
  const billing = params.get('billing') || ''
  const [q, setQ] = useState(params.get('q') || '')
  const page = Number(params.get('page') || 1)
  const qs = new URLSearchParams({ status, page, pagesize: 100 })
  for (const k of ['billing', 'q', 'driverid', 'vehicleid']) if (params.get(k)) qs.set(k, params.get(k))
  const [data, error, reload] = useLoad(() => api.get(`/trips?${qs}`), [qs.toString()])
  const [booking, setBooking] = useState(false)

  const set = (k, v) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v); else next.delete(k)
    if (k !== 'page') next.delete('page')
    setParams(next)
  }

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <h1>Trips</h1>
          <div className="muted">Every trip, checked against the credentials in force at its pickup time.</div>
        </div>
        {/* The office books by telephone as well as receiving broker files, and until the
            import exists this is the only way a trip gets into the system at all. */}
        <button type="button" className="primary" onClick={() => setBooking(true)}>
          <Plus size={14} /> Book A Trip
        </button>
      </div>
      {booking && (
        <BookTrip onClose={() => setBooking(false)}
          onBooked={() => { setBooking(false); reload() }} />
      )}
      <div className="row">
        <div className="seg">
          {[['fail', 'At risk'], ['pass', 'Credentialed'], ['all', 'All']].map(([v, l]) => (
            <button key={v} className={status === v ? 'on' : ''} onClick={() => set('status', v)}>{l}</button>
          ))}
        </div>
        <select value={billing} onChange={(e) => set('billing', e.target.value)}>
          <option value="">Any billing status</option>
          <option value="unbilled">Unbilled</option>
          <option value="held">Held</option>
          <option value="billed">Billed</option>
          <option value="paid">Paid</option>
        </select>
        <form onSubmit={(e) => { e.preventDefault(); set('q', q) }} className="row">
          <input placeholder="Trip number" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        {(params.get('driverid') || params.get('vehicleid')) && (
          <button onClick={() => { const n = new URLSearchParams(params); n.delete('driverid'); n.delete('vehicleid'); setParams(n) }}>
            Showing one {params.get('driverid') ? 'driver' : 'vehicle'} · clear
          </button>
        )}
      </div>
      {!data ? <Loading error={error} /> : (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{count(data.total)} trips, {money(data.amount)} billed</div>
          <div className="tablewrap"><table>
            <thead><tr><th>Trip</th><th>Date</th><th>Broker</th><th>Driver</th><th>Status</th><th>Why</th><th>Billing</th><th className="num">Billed</th></tr></thead>
            <tbody>{data.items.map((t) => (
              <tr key={t.recordid} className="click" onClick={() => navigate(`/trips/${t.recordid}`)}>
                <td>{t.externalid}</td>
                <td>{date(t.tripdate)}</td>
                <td>{t.broker || '-'}</td>
                <td>{t.drivers || '-'}</td>
                <td>{t.failures ? <Badge state="atrisk" /> : <Badge state="clean" />}</td>
                <td className="small" style={{ maxWidth: 360 }}>{t.reasons || ''}</td>
                <td>{t.billingstatus}</td>
                <td className="num">{money(t.billedamount)}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {data.total > data.pagesize && (
            <div className="row" style={{ marginTop: 12 }}>
              <button disabled={page <= 1} onClick={() => set('page', page - 1)}>Previous</button>
              <span className="muted small">Page {page} of {Math.ceil(data.total / data.pagesize)}</span>
              <button disabled={page * data.pagesize >= data.total} onClick={() => set('page', page + 1)}>Next</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
