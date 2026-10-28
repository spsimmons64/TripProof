import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Download, Package } from 'lucide-react'
import { api } from '../lib/api.js'
import { bytes, date, datetime, tzDateTime } from '../lib/format.js'
import { Loading, useLoad } from '../components/ui.jsx'

export default function AuditDetail() {
  const { id } = useParams()
  const [a, error, reload] = useLoad(() => api.get(`/audits/${id}`), [id])
  const [trips, setTrips] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)
  if (!a) return <Loading error={error} page />

  const generate = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null); setResult(null)
    try { setResult(await api.post('/packets', { trips, auditrequestid: id })); reload() }
    catch (e2) { setErr(e2.message) } finally { setBusy(false) }
  }
  const setStatus = async (status) => { await api.patch(`/audits/${id}`, { status }); reload() }

  return (
    <div className="stack">
      <div className="pagehead">
        <div>
          <div className="small"><Link to="/audits">Audits</Link></div>
          <h1>{a.requester}{a.reference ? ` · ${a.reference}` : ''}</h1>
          <div className="muted">Received {date(a.receivedon)}{a.dueon ? ` · due ${date(a.dueon)}` : ''} · {a.status}</div>
        </div>
        <div className="row">
          {a.status !== 'submitted' && <button onClick={() => setStatus('submitted')}>Mark submitted</button>}
          {a.status !== 'closed' && <button onClick={() => setStatus('closed')}>Close</button>}
        </div>
      </div>
      {a.notes && <div className="card">{a.notes}</div>}

      <form className="card stack" onSubmit={generate}>
        <h2>Build an evidence packet</h2>
        <label className="field">Trip numbers the auditor requested - paste them as listed (commas, spaces or one per line). Ranges like T1001-T1100 expand.
          <textarea value={trips} onChange={(e) => setTrips(e.target.value)} required />
        </label>
        <div className="small muted">Each trip is re-checked against the vault as it stands now; the packet records that check run and a SHA-256 digest of itself.</div>
        {err && <div className="notice bad"><AlertTriangle size={16} /> {err}</div>}
        {result && (
          <div className={`notice ${result.failedtrips ? 'warn' : 'good'}`}>
            {result.failedtrips ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
            <div>Packet built for {result.tripcount} trips - {result.tripcount - result.failedtrips} fully credentialed, {result.failedtrips} not.
              {result.notfound.length > 0 && ` Not in the ledger: ${result.notfound.slice(0, 20).join(', ')}${result.notfound.length > 20 ? '…' : ''}.`}</div>
          </div>
        )}
        <div><button className="primary" disabled={busy}><Package size={14} /> {busy ? 'Building…' : 'Build packet'}</button></div>
      </form>

      <div className="card">
        <h2>Packets</h2>
        {a.packets.length === 0 ? <div className="muted">None yet.</div> : (
          <div className="tablewrap"><table>
            <thead><tr><th>Built</th><th>By</th><th className="num">Trips</th><th>Size</th><th>SHA-256</th><th /></tr></thead>
            <tbody>{a.packets.map((p) => (
              <tr key={p.recordid}>
                <td>{tzDateTime(p.added)}</td><td>{p.generatedby}</td><td className="num">{p.tripcount}</td><td>{bytes(p.bytes)}</td>
                <td title={p.sha256}>{p.sha256.slice(0, 16)}…</td>
                <td><button onClick={() => api.download(`/packets/${p.recordid}/download`, 'packet.zip')}><Download size={14} /> Download</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  )
}
