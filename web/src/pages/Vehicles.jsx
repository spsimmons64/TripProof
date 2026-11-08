import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { money } from '../lib/format.js'
import { Badge, useLoad } from '../components/ui.jsx'
import { useUser } from '../App.jsx'
import DataGrid, { useGridParams } from '../components/DataGrid.jsx'

// The same seven columns the fleet always had, now in the grid every other list on the site uses.
// `/vehicles` answers with the whole fleet rather than a page of it, so the sorting and the paging
// are done here - the same way the Users list does it, and for the same reason.
const COLUMNS = [
  { id: 'externalid', label: 'Unit', width: 120 },
  { id: 'vehicle', label: 'Vehicle', sortable: false },
  { id: 'vin', label: 'VIN', width: 190 },
  { id: 'compliance', label: 'Compliance', width: 190, sortable: false },
  { id: 'risktrips', label: 'Trips at risk', width: 130, numeric: true },
  { id: 'riskamount', label: 'At risk', width: 130, numeric: true },
]

export default function Vehicles() {
  const [data, error, reload] = useLoad(() => api.get('/vehicles'))
  // What each unit still owes, from the same engine the driver roster reads. Loaded beside the
  // list rather than inside it so one slow answer cannot hold up the fleet.
  const [owed] = useLoad(() => api.get('/vehicles/requirements'))
  const owing = new Map((owed?.vehicles || []).map((v) => [v.recordid, v]))
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  const g = useGridParams({ defaultSort: 'externalid', defaultDir: 'asc' })

  const all = data || []
  const flip = g.dir === 'desc' ? -1 : 1
  const shown = [...all].sort((a, b) => {
    const x = a[g.sort] ?? '', y = b[g.sort] ?? ''
    if (x === y) return String(a.externalid || '').localeCompare(String(b.externalid || ''))
    // Numbers compare as numbers; a unit number compares as the text it is printed as.
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * flip
    return String(x).localeCompare(String(y), undefined, { numeric: true }) * flip
  })
  const page = shown.slice((g.page - 1) * g.pagesize, g.page * g.pagesize)

  return (
    <div className="fill">
      <div className="pagehead">
        <div><h1>Vehicles</h1></div>
        <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add vehicle</button>
      </div>
      {adding && <VehicleForm onCancel={() => setAdding(false)}
        onDone={(id) => { setAdding(false); if (id) navigate(`/vehicles/${id}`); else reload() }} />}

      <DataGrid columns={COLUMNS} rows={data && page} rowKey={(v) => v.recordid} error={error}
        sort={g.sort} dir={g.dir} onSort={g.onSort}
        onRowClick={(v) => navigate(`/vehicles/${v.recordid}`)}
        pager={data && g.pager(shown.length, 'vehicle')}
        empty="No vehicles yet."
        cells={(v) => [
          <>{v.externalid || '-'} {v.stub ? <Badge state="stub" /> : null}</>,
          [v.modelyear, v.make, v.model].filter(Boolean).join(' ') || '-',
          v.vin || '-',
          <FleetStanding owed={owing.get(v.recordid)} />,
          v.risktrips,
          money(v.riskamount),
        ]} />
    </div>
  )
}

// What one unit owes, in the same three words the roster uses. A hard stop is named as a stop
// because that is the one a reader has to act on today.
function FleetStanding({ owed }) {
  if (!owed) return <span className="muted small">-</span>
  if (owed.stops.length) {
    return <span className="st-expired">{owed.stops.length} stopping this vehicle</span>
  }
  if (owed.outstanding.length) {
    return <span className="st-ordered">{owed.outstanding.length} outstanding</span>
  }
  if (owed.expiring.length) {
    return <span className="st-ordered">{owed.expiring.length} expiring</span>
  }
  return <span className="st-active">In order</span>
}

// `onCancel` is what there is to go back to. On the vehicle's own page the form IS the page, so
// there is nothing to cancel into and no Cancel button is drawn.
export function VehicleForm({ initial = {}, id, onDone, onCancel }) {
  const [f, setF] = useState({ externalid: '', vin: '', plate: '', make: '', model: '', modelyear: '',
    seats: '', gvwr: '', gcwr: '', lift: false, odometer: '',
    odometerasof: '', ...initial })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  // The vehicle's transit safety program determinations, set here on the vehicle rather than in a
  // table on the company's page. Owners and admins decide them. FMCSA is in DOT & CDL Setup.
  const decides = ['owner', 'admin'].includes(useUser()?.role)
  const [det] = useLoad(() => (decides ? api.get(`/company/operating-profile/vehicles/${id || 'new'}`)
    : Promise.resolve(null)), [id])
  const [picked, setPicked] = useState({})
  const transitOf = (code) => (picked[code] !== undefined ? picked[code] : (det?.transit[code] || ''))
  const saveDeterminations = async (vehicleid) => {
    if (!det) return
    for (const p of det.programs) {
      if (picked[p.code] !== undefined && picked[p.code] !== (det.transit[p.code] || '')) {
        await api.put(`/company/operating-profile/vehicles/${vehicleid}/transit/${p.code}`,
          { determination: picked[p.code] || null })
      }
    }
  }
  const submit = async (e) => {
    e.preventDefault()
    const keys = ['externalid', 'vin', 'plate', 'make', 'model', 'modelyear', 'seats', 'gvwr',
      'gcwr', 'odometer', 'odometerasof']
    const body = Object.fromEntries(keys.map((k) => [k, f[k] === '' || f[k] === undefined ? null : f[k]]))
    body.modelyear = body.modelyear ? Number(body.modelyear) : null
    body.seats = body.seats ? Number(body.seats) : null
    body.gvwr = body.gvwr ? Number(body.gvwr) : null
    body.gcwr = body.gcwr ? Number(body.gcwr) : null
    body.lift = Boolean(f.lift)
    body.odometer = body.odometer ? Number(body.odometer) : null
    try {
      if (id) { await api.put(`/vehicles/${id}`, body); await saveDeterminations(id); onDone() }
      else {
        const made = (await api.post('/vehicles', body)).recordid
        await saveDeterminations(made)
        onDone(made)
      }
    } catch (err) { setError(err.message) }
  }
  return (
    <form className="card qualcard" onSubmit={submit}>
      {/* The same head the panels under it wear, with what finishes the panel at its right - the
          driver's own record is read and saved this way, and this is the same act on a vehicle. */}
      <div className="infotabs">
        <h3>{id ? 'Vehicle' : 'Add A Vehicle'}</h3>
        <div className="row">
          {onCancel && <button type="button" onClick={onCancel}>Cancel</button>}
          <button className="primary">Save</button>
        </div>
      </div>
      {/* Three sections, one kind of thing to a row: what the vehicle is, what it carries, and what
          has been determined about it. */}
      <div className="infoform stack">
        <div>
          <h3 className="formsection">Identification</h3>
          <div className="profileform">
            <label className="field">Unit Number (Dispatch)<input value={f.externalid || ''} onChange={set('externalid')} /></label>
            <label className="field">VIN<input maxLength={17} value={f.vin || ''} onChange={set('vin')} /></label>
            <label className="field">Plate<input value={f.plate || ''} onChange={set('plate')} /></label>
            <label className="field">Model Year<input type="number" min="1980" max="2100" value={f.modelyear || ''} onChange={set('modelyear')} /></label>
            <label className="field">Make<input value={f.make || ''} onChange={set('make')} /></label>
            <label className="field">Model<input value={f.model || ''} onChange={set('model')} /></label>
          </div>
        </div>
        {/* Seats and the weight ratings decide what the vehicle is - a commercial motor vehicle
            federally or under Florida law, and what license its driver needs. They are measurements,
            not judgements; what they add up to is worked out and shown on the vehicle. */}
        <div>
          <h3 className="formsection">Capacity And Equipment</h3>
          <div className="profileform">
            <label className="field">Seats, Including The Driver
              <input type="number" min="1" max="99" value={f.seats || ''} onChange={set('seats')} /></label>
            <label className="field">GVWR (lb)
              <input type="number" min="0" max="120000" value={f.gvwr || ''} onChange={set('gvwr')} /></label>
            <label className="field">GCWR (lb), If It Tows
              <input type="number" min="0" max="120000" value={f.gcwr || ''} onChange={set('gcwr')} /></label>
            <label className="field">Wheelchair Lift Or Ramp
              <select value={f.lift ? 'yes' : 'no'} onChange={(e) => setF({ ...f, lift: e.target.value === 'yes' })}>
                <option value="yes">Yes</option><option value="no">No</option>
              </select></label>
            <label className="field">Odometer (Miles)<input type="number" min="0" value={f.odometer || ''} onChange={set('odometer')} /></label>
            <label className="field">Odometer Read On<input type="date" value={f.odometerasof || ''} onChange={set('odometerasof')} /></label>
          </div>
        </div>
        {det && det.programs.length > 0 && (
          <div>
            <h3 className="formsection">Determinations</h3>
            <div className="profileform">
              {det.programs.map((p) => (
                <label key={p.code} className="field span-2">
                  {`${p.name} (${p.state} ${(p.citation || '').split(' ').pop()})`}
                  <select value={transitOf(p.code)} onChange={(e) => setPicked({ ...picked, [p.code]: e.target.value })}>
                    <option value="">Not determined</option>
                    {Object.entries(det.choices).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                  </select></label>
              ))}
            </div>
          </div>
        )}
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  )
}
