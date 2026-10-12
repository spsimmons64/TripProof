import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Upload } from 'lucide-react'
import { api } from '../lib/api.js'
import { count, date, datetime, money, tzDateTime } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'

const FIELD_LABELS = {
  tripid: 'Trip number *', leg: 'Leg number', tripdate: 'Date of service', pickupat: 'Pickup time *', dropoffat: 'Drop-off time',
  driverid: 'Driver ID', drivername: 'Driver name', vehicleid: 'Vehicle / unit', vin: 'VIN', broker: 'Broker / payer',
  servicelevel: 'Service level', billedamount: 'Billed amount', billingstatus: 'Billing status', memberid: 'Member ID',
  membername: 'Member name', memberdob: 'Member DOB', pickupaddress: 'Pickup address', dropoffaddress: 'Drop-off address',
  signature: 'Signature captured', gps: 'GPS captured',
}

// Upload -> preview (with a chance to fix column matches) -> accept. Nothing touches the ledger
// until Accept, and accepting writes exactly what the preview showed.
export default function Import() {
  const [file, setFile] = useState(null)
  const [batch, setBatch] = useState(null)
  const [mapping, setMapping] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [over, setOver] = useState(false)
  const [result, setResult] = useState(null)
  const input = useRef()
  const navigate = useNavigate()
  const [history, , reloadHistory] = useLoad(() => api.get('/imports'))

  const stage = async (f, map) => {
    setBusy(true); setError(null); setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', f)
      if (map) fd.append('mapping', JSON.stringify(map))
      const b = await api.post('/imports', fd)
      setBatch(b)
      setMapping(b.mapping || {})
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const pick = (f) => { if (f) { setFile(f); stage(f) } }
  const accept = async () => {
    setBusy(true); setError(null)
    try { setResult(await api.post(`/imports/${batch.recordid}/accept`)); setBatch(null); setFile(null); reloadHistory() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const reject = async () => { await api.post(`/imports/${batch.recordid}/reject`); setBatch(null); setFile(null); reloadHistory() }

  const s = batch?.summary
  return (
    <div className="stack">
      <div className="pagehead"><div>
        <h1>Import trips</h1>
        <div className="muted">Upload the trip export from your dispatch system (CSV). Columns are matched automatically; you can correct any match before accepting.</div>
      </div></div>

      {result && (
        <div className="notice good"><CheckCircle2 size={16} /><div>
          Imported {count(result.trips)} trips ({count(result.legs)} legs){result.skipped ? `, skipped ${count(result.skipped)} rows for trips already in the ledger` : ''}.
          {result.driverscreated + result.vehiclescreated > 0 && ` Added ${result.driverscreated} drivers and ${result.vehiclescreated} vehicles that need their credentials entered.`}
          {' '}{count(result.evaluation.failures)} failed checks. <a href="#" onClick={(e) => { e.preventDefault(); navigate('/') }}>See exposure</a>
        </div></div>
      )}
      {error && <div className="notice bad"><AlertTriangle size={16} /> {error}</div>}

      {!batch && (
        <div className={`drop${over ? ' over' : ''}`} onClick={() => input.current.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}>
          <Upload size={28} /><div style={{ marginTop: 8 }}>{busy ? 'Reading file…' : 'Drop a CSV here, or click to choose'}</div>
          <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={(e) => pick(e.target.files[0])} />
        </div>
      )}

      {batch && (
        <>
          <div className="card stack">
            <h2>Preview: {batch.filename}</h2>
            {s ? (
              <div className="grid cols-4">
                <div><div className="muted small">Trips</div><b>{count(s.tripcount)}</b> ({count(s.newtrips)} new{s.duplicatetrips ? `, ${count(s.duplicatetrips)} already imported` : ''})</div>
                <div><div className="muted small">Dates</div><b>{s.daterange ? `${date(s.daterange[0])} - ${date(s.daterange[1])}` : '-'}</b></div>
                <div><div className="muted small">Billed</div><b>{money(s.totalbilled)}</b></div>
                <div><div className="muted small">Rows</div><b>{count(s.rowcount)}</b>{batch.errors.length ? <span className="error"> · {batch.errors.length} skipped</span> : ''}</div>
              </div>
            ) : null}
            {s?.newdrivers?.length > 0 && <div className="notice warn"><AlertTriangle size={16} /><div>{s.newdrivers.length} drivers are not in your vault yet and will be added as incomplete records: {s.newdrivers.slice(0, 15).join(', ')}{s.newdrivers.length > 15 ? '…' : ''}</div></div>}
            {s?.newvehicles?.length > 0 && <div className="notice warn"><AlertTriangle size={16} /><div>{s.newvehicles.length} vehicles will be added as incomplete records: {s.newvehicles.slice(0, 15).join(', ')}{s.newvehicles.length > 15 ? '…' : ''}</div></div>}
            {s?.brokersunmatched?.length > 0 && <div className="notice warn"><AlertTriangle size={16} /><div>Unrecognised brokers (only state baseline rules will apply): {s.brokersunmatched.join(', ')}</div></div>}
            {batch.errors.length > 0 && (
              <details><summary>{batch.errors.length} rows could not be read</summary>
                <ul className="small">{batch.errors.slice(0, 50).map((e, i) => <li key={i}>Row {e.row}: {e.error}</li>)}</ul>
              </details>
            )}
            <div className="row">
              <button className="primary" onClick={accept} disabled={busy || !s || s.newtrips === 0}>{busy ? 'Working…' : `Accept ${s ? count(s.newtrips) : ''} trips`}</button>
              <button onClick={reject} disabled={busy}>Discard</button>
            </div>
          </div>

          <div className="card stack">
            <h2>Column matches</h2>
            <div className="form">
              {batch.fields.map((f) => (
                <label className="field" key={f}>{FIELD_LABELS[f] || f}
                  <select value={mapping[f] || ''} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || undefined })}>
                    <option value="">- not in file -</option>
                    {(batch.headers || []).map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </label>
              ))}
            </div>
            <div><button onClick={() => stage(file, mapping)} disabled={busy || !file}>Re-read with these matches</button></div>
          </div>
        </>
      )}

      <div className="card">
        <h2>Recent imports</h2>
        {!history ? <Loading /> : history.length === 0 ? <div className="muted">None yet.</div> : (
          <div className="tablewrap"><table>
            <thead><tr><th>File</th><th>Uploaded</th><th>Status</th><th className="num">Trips</th></tr></thead>
            <tbody>{history.map((h) => (
              <tr key={h.recordid}><td>{h.filename}</td><td>{tzDateTime(h.added)}</td>
                <td><Badge state={h.status === 'accepted' ? 'pass' : h.status === 'rejected' ? 'neutral' : 'pending'}>{h.status}</Badge></td>
                <td className="num">{count(h.tripcount)}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  )
}
