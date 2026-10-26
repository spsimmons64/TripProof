import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, Search } from 'lucide-react'
import { api } from '../lib/api.js'
import { count, date, money } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import BookTrip from '../components/BookTrip.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'

// The same eight columns, in the grid every other list on the site uses. Why is prose and carries
// the reasons a trip failed, so it is the one column that wraps rather than being clipped.
const COLUMNS = [
  { id: 'externalid', label: 'Trip', width: 130 },
  { id: 'tripdate', label: 'Date', width: 120 },
  { id: 'broker', label: 'Payer', width: 150 },
  { id: 'drivers', label: 'Driver', width: 180 },
  { id: 'failures', label: 'Status', width: 120 },
  { id: 'reasons', label: 'Why', sortable: false },
  { id: 'billingstatus', label: 'Billing', width: 120 },
  { id: 'billedamount', label: 'Billed', width: 120, numeric: true },
]

const BILLING = [['', 'Any billing status'], ['unbilled', 'Unbilled'], ['held', 'Held'],
                 ['billed', 'Billed'], ['paid', 'Paid']]

// The pre-billing scrub: filter to unbilled + at risk and fix each one before it goes out the door.
export default function Trips() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const g = useGridParams({ filters: ['status', 'billing', 'driverid', 'vehicleid'],
                            defaultSort: 'tripdate', defaultDir: 'desc' })
  // Trips open on what needs work, not on everything: the scrub is the job this page exists for.
  const status = g.filters.status || 'fail'
  const query = g.query.includes('status=') ? g.query : `${g.query}&status=${status}`
  const [data, error, reload] = useLoad(() => api.get(`/trips?${query}`), [query])
  const [booking, setBooking] = useState(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (data) g.fitPage(data.total) }, [data])

  return (
    <div className="fill">
      <div className="pagehead">
        <div><h1>Trips</h1></div>
        <div className="row">
          <div className="searchbox"><Search size={14} /><input placeholder="Search Trips"
            value={g.search} onChange={(e) => g.setSearch(e.target.value)} /></div>
          {/* The office books by telephone as well as receiving broker files, and until the
              import exists this is the only way a trip gets into the system at all. */}
          <button type="button" className="primary" onClick={() => setBooking(true)}>
            <Plus size={14} /> Book A Trip
          </button>
        </div>
      </div>
      {booking && (
        <BookTrip onClose={() => setBooking(false)}
          onBooked={() => { setBooking(false); reload() }} />
      )}

      <div className="filterrow">
        <div className="segs">
          {[['fail', 'At Risk'], ['pass', 'Credentialed'], ['all', 'All']].map(([v, l]) => (
            <button key={v} type="button" className={`chip${status === v ? ' on' : ''}`}
              onClick={() => g.setFilter('status', v)}>{l}</button>
          ))}
        </div>
        <select value={g.filters.billing} onChange={(e) => g.setFilter('billing', e.target.value)}>
          {BILLING.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {(g.filters.driverid || g.filters.vehicleid) && (
          <button type="button" onClick={() => {
            const n = new URLSearchParams(params); n.delete('driverid'); n.delete('vehicleid')
            setParams(n)
          }}>Showing one {g.filters.driverid ? 'driver' : 'vehicle'} · clear</button>
        )}
        {data && (
          <span className="muted small">{count(data.total)} trips, {money(data.amount)} billed</span>
        )}
      </div>

      <DataGrid columns={COLUMNS} rows={data?.items} rowKey={(t) => t.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        onRowClick={(t) => navigate(`/trips/${t.recordid}`)}
        pager={data && g.pager(data.total, 'trip')}
        empty={g.filtered ? 'No trips match this filter.' : 'No trips yet.'}
        cells={(t) => [
          t.externalid,
          date(t.tripdate),
          t.broker || '-',
          t.drivers || '-',
          t.failures ? <Badge state="atrisk" /> : <Badge state="clean" />,
          t.reasons || '',
          t.billingstatus,
          money(t.billedamount),
        ]} />
    </div>
  )
}
