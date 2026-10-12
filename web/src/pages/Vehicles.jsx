import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { money } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'
import { CredentialSummary } from './Drivers.jsx'

export default function Vehicles() {
  const [data, error, reload] = useLoad(() => api.get('/vehicles'))
  // What each unit still owes, from the same engine the driver roster reads. Loaded beside the
  // list rather than inside it so one slow answer cannot hold up the fleet.
  const [owed] = useLoad(() => api.get('/vehicles/requirements'))
  const owing = new Map((owed?.vehicles || []).map((v) => [v.recordid, v]))
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  return (
    <div className="stack">
      <div className="pagehead">
        <div><h1>Vehicles</h1><div className="muted">Every unit that has run a trip.</div></div>
        <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add vehicle</button>
      </div>
      {adding && <VehicleForm onDone={(id) => { setAdding(false); if (id) navigate(`/vehicles/${id}`); else reload() }} />}
      {!data ? <Loading error={error} /> : (
        <div className="card"><div className="tablewrap"><table>
          <thead><tr><th>Unit</th><th>Vehicle</th><th>VIN</th><th>Compliance</th><th>Credentials</th><th className="num">Trips at risk</th><th className="num">At risk</th></tr></thead>
          <tbody>{data.map((v) => (
            <tr key={v.recordid} className="click" onClick={() => navigate(`/vehicles/${v.recordid}`)}>
              <td>{v.externalid || '-'} {v.stub ? <Badge state="stub" /> : null}</td>
              <td>{[v.modelyear, v.make, v.model].filter(Boolean).join(' ') || '-'}</td>
              <td>{v.vin || '-'}</td>
              <td><FleetStanding owed={owing.get(v.recordid)} /></td>
              <td><CredentialSummary r={v} /></td>
              <td className="num">{v.risktrips}</td>
              <td className="num">{money(v.riskamount)}</td>
            </tr>
          ))}</tbody>
        </table></div></div>
      )}
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

export function VehicleForm({ initial = {}, id, onDone }) {
  const [f, setF] = useState({ externalid: '', vin: '', plate: '', make: '', model: '', modelyear: '',
    seats: '', gvwr: '', gcwr: '', forcompensation: false, lift: false, odometer: '',
    odometerasof: '', ...initial })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    const keys = ['externalid', 'vin', 'plate', 'make', 'model', 'modelyear', 'seats', 'gvwr',
      'gcwr', 'odometer', 'odometerasof']
    const body = Object.fromEntries(keys.map((k) => [k, f[k] === '' || f[k] === undefined ? null : f[k]]))
    body.modelyear = body.modelyear ? Number(body.modelyear) : null
    body.seats = body.seats ? Number(body.seats) : null
    body.gvwr = body.gvwr ? Number(body.gvwr) : null
    body.gcwr = body.gcwr ? Number(body.gcwr) : null
    body.forcompensation = Boolean(f.forcompensation)
    body.lift = Boolean(f.lift)
    body.odometer = body.odometer ? Number(body.odometer) : null
    try {
      if (id) { await api.put(`/vehicles/${id}`, body); onDone() }
      else onDone((await api.post('/vehicles', body)).recordid)
    } catch (err) { setError(err.message) }
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <div className="form">
        <label className="field">Unit number (dispatch)<input value={f.externalid || ''} onChange={set('externalid')} /></label>
        <label className="field">VIN<input maxLength={17} value={f.vin || ''} onChange={set('vin')} /></label>
        <label className="field">Plate<input value={f.plate || ''} onChange={set('plate')} /></label>
        <label className="field">Model year<input type="number" min="1980" max="2100" value={f.modelyear || ''} onChange={set('modelyear')} /></label>
        <label className="field">Make<input value={f.make || ''} onChange={set('make')} /></label>
        <label className="field">Model<input value={f.model || ''} onChange={set('model')} /></label>
        {/* These four decide what the vehicle is, and everything downstream follows from them:
            whether it is a commercial motor vehicle federally, whether it is one under Florida law,
            and what licence its driver needs. They are measurements, not judgements - what they add
            up to is worked out and shown on the vehicle, never typed in. */}
        <label className="field">Seats, including the driver
          <input type="number" min="1" max="99" value={f.seats || ''} onChange={set('seats')} /></label>
        <label className="field">GVWR (lb)
          <input type="number" min="0" max="120000" value={f.gvwr || ''} onChange={set('gvwr')} /></label>
        <label className="field">GCWR (lb), if it tows
          <input type="number" min="0" max="120000" value={f.gcwr || ''} onChange={set('gcwr')} /></label>
        <label className="field check span-3">
          <input type="checkbox" checked={Boolean(f.forcompensation)}
            onChange={(e) => setF({ ...f, forcompensation: e.target.checked })} />
          Passengers are carried for compensation
        </label>
        <label className="field check span-3">
          <input type="checkbox" checked={Boolean(f.lift)}
            onChange={(e) => setF({ ...f, lift: e.target.checked })} /> Wheelchair lift or ramp
        </label>
        <label className="field">Odometer (miles)<input type="number" min="0" value={f.odometer || ''} onChange={set('odometer')} /></label>
        <label className="field">Odometer read on<input type="date" value={f.odometerasof || ''} onChange={set('odometerasof')} /></label>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row"><button className="primary">Save</button><button type="button" onClick={() => onDone()}>Cancel</button></div>
    </form>
  )
}
