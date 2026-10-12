import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '../lib/api.js'
import { date } from '../lib/format.js'
import { Badge, Loading, useLoad } from '../components/ui.jsx'

export default function Audits() {
  const [data, error, reload] = useLoad(() => api.get('/audits'))
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ requester: '', reference: '', receivedon: new Date().toISOString().slice(0, 10), dueon: '', notes: '' })
  const [err, setErr] = useState(null)
  const navigate = useNavigate()
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    try {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === '' ? null : v]))
      const { recordid } = await api.post('/audits', body)
      navigate(`/audits/${recordid}`)
    } catch (e2) { setErr(e2.message) }
  }

  return (
    <div className="stack">
      <div className="pagehead">
        <div><h1>Audits</h1><div className="muted">Record each records request, then answer it with an evidence packet.</div></div>
        <button className="primary" onClick={() => setAdding(true)}><Plus size={14} /> New request</button>
      </div>
      {adding && (
        <form className="card stack" onSubmit={submit}>
          <div className="form">
            <label className="field">Requested by *<input required value={f.requester} onChange={set('requester')} /></label>
            <label className="field">Their reference<input value={f.reference} onChange={set('reference')} /></label>
            <label className="field">Received *<input type="date" required value={f.receivedon} onChange={set('receivedon')} /></label>
            <label className="field">Due<input type="date" value={f.dueon} onChange={set('dueon')} /></label>
          </div>
          <label className="field">Notes<textarea value={f.notes} onChange={set('notes')} /></label>
          {err && <div className="error">{err}</div>}
          <div className="row"><button className="primary">Create</button><button type="button" onClick={() => { setAdding(false); reload() }}>Cancel</button></div>
        </form>
      )}
      {!data ? <Loading error={error} /> : (
        <div className="card">
          {data.length === 0 ? <div className="muted">No audit requests yet.</div> : (
            <div className="tablewrap"><table>
              <thead><tr><th>Requested by</th><th>Reference</th><th>Received</th><th>Due</th><th>Status</th><th className="num">Packets</th></tr></thead>
              <tbody>{data.map((a) => (
                <tr key={a.recordid} className="click" onClick={() => navigate(`/audits/${a.recordid}`)}>
                  <td>{a.requester}</td><td>{a.reference || '-'}</td><td>{date(a.receivedon)}</td><td>{date(a.dueon)}</td>
                  <td><Badge state={a.status === 'closed' ? 'pass' : a.status === 'submitted' ? 'current' : 'expiring'}>{a.status}</Badge></td>
                  <td className="num">{a.packets}</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </div>
      )}
    </div>
  )
}
